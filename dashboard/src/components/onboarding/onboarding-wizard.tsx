"use client"

/**
 * Track 2 **onboarding wizard shell** (Phase 5a–b).
 *
 * - Owns high-level step navigation + a progress indicator.
 * - Runs the Gmail → discovery → identity → optional LLM keys → sequential backfill
 *   (with automatic chunk polling) → gap review → goals → summary pipeline.
 * - The same component is mounted full-screen from ``/setup`` **and** inside the
 *   Settings sheet for **Connect account** — pass ``mode`` + ``className`` only.
 */

import * as React from "react"

import { GoalTemplateWizard } from "@/components/onboarding/goal-template-wizard"
import { OnboardingOptionalLlmKeys } from "@/components/onboarding/onboarding-optional-llm-keys"
import { PreClassificationForm } from "@/components/onboarding/pre-classification-form"
import { StepBackfill, type BackfillProgressSnapshot } from "@/components/onboarding/step-backfill"
import { StepClassification } from "@/components/onboarding/step-classification"
import { StepDiscovery } from "@/components/onboarding/step-discovery"
import { StepGapDetection } from "@/components/onboarding/step-gap-detection"
import { StepSummary } from "@/components/onboarding/step-summary"
import { StepWelcome } from "@/components/onboarding/step-welcome"
import { Button } from "@/components/ui/button"
import {
  fetchOnboardingBackfillProgress,
  patchOnboardingState,
  postOnboardingBackfillChunk,
  postOnboardingBackfillResume,
} from "@/lib/api"
import { cn } from "@/lib/utils"
import { humanizeSourceKey } from "@/lib/source-label"
import { useOnboardingBackfillSources, useOnboardingState } from "@/hooks/use-onboarding"
import { getUserFacingErrorMessage } from "@/lib/user-facing-api-error"

export type WizardStepId =
  | "welcome"
  | "discovery"
  | "preclass"
  | "apikey"
  | "backfill"
  | "classification"
  | "gaps"
  | "goals"
  | "summary"

const STEP_META: { id: WizardStepId; label: string }[] = [
  { id: "welcome", label: "Gmail" },
  { id: "discovery", label: "Find accounts" },
  { id: "preclass", label: "Your name" },
  { id: "apikey", label: "Smart labels (opt.)" },
  { id: "backfill", label: "Import mail" },
  { id: "classification", label: "Review" },
  { id: "gaps", label: "Coverage" },
  { id: "goals", label: "Goals" },
  { id: "summary", label: "Done" },
]

/** Valid wizard step ids — used to safely resume ``current_step`` from the server. */
const WIZARD_STEP_IDS = new Set<WizardStepId>(STEP_META.map((s) => s.id))

/**
 * Map persisted ``OnboardingState.current_step`` to the in-memory panel id.
 * ``classification`` needs ``classifySource`` in React state — resume via backfill loop instead.
 * ``completed`` means the user finished — start a fresh connect-account flow at welcome.
 */
function panelFromServerStep(step: string): WizardStepId {
  if (step === "classification") {
    return "backfill"
  }
  if (step === "completed") {
    return "welcome"
  }
  if (WIZARD_STEP_IDS.has(step as WizardStepId)) {
    return step as WizardStepId
  }
  return "welcome"
}

export type OnboardingWizardProps = {
  mode: "setup" | "settings"
  className?: string
  /** Fires after ``POST /api/onboarding/complete`` succeeds. */
  onFinished: () => void
  /** Optional — first-step **Back** (e.g. return to PDF secrets on ``/setup``). */
  onExitFirstStep?: () => void
}

export function OnboardingWizard({
  mode,
  className,
  onFinished,
  onExitFirstStep,
}: OnboardingWizardProps) {
  const stateQ = useOnboardingState()
  /**
   * Server-resumed step from ``GET /state`` (null while the query is still loading).
   * We derive the visible step below so we **do not** need a hydration effect that calls
   * setState — that pattern triggers ``react-hooks/set-state-in-effect``.
   */
  const serverPanel = React.useMemo((): WizardStepId | null => {
    if (stateQ.isLoading) return null
    return panelFromServerStep(stateQ.data?.current_step ?? "welcome")
  }, [stateQ.isLoading, stateQ.data])
  /**
   * Once the user moves forward/back in the wizard, this override wins over ``serverPanel``
   * for the rest of the session (same as “we already hydrated from the server” before).
   */
  const [userPanel, setUserPanel] = React.useState<WizardStepId | null>(null)
  const panel: WizardStepId = userPanel ?? serverPanel ?? "welcome"
  const sourcesQ = useOnboardingBackfillSources()
  const prevPanelRef = React.useRef<WizardStepId | null>(null)

  const [bfSourceIdx, setBfSourceIdx] = React.useState(0)
  const [bfTick, setBfTick] = React.useState(0)
  const [bfProgress, setBfProgress] = React.useState<BackfillProgressSnapshot | null>(null)
  const [bfError, setBfError] = React.useState<string | null>(null)
  const [classifySource, setClassifySource] = React.useState<string | null>(null)
  const [resumeBusy, setResumeBusy] = React.useState(false)

  const activeSourceKey = sourcesQ.data?.[bfSourceIdx]?.source_key ?? null
  const activeSourceLabel = activeSourceKey ? humanizeSourceKey(activeSourceKey) : null

  // Persist coarse wizard position so a refresh mid-flow still shows the same step name.
  // Skip while onboarding state is still loading and the user has not navigated yet — otherwise
  // we would PATCH the default ``welcome`` over the real server step.
  React.useEffect(() => {
    if (stateQ.isLoading && userPanel === null) return
    void patchOnboardingState({ current_step: panel }).catch(() => {
      /* non-fatal */
    })
  }, [panel, stateQ.isLoading, userPanel])

  // When entering backfill from earlier setup steps, restart the source queue.
  React.useEffect(() => {
    const prev = prevPanelRef.current
    prevPanelRef.current = panel
    if (panel !== "backfill") return
    if (prev === "classification" || prev === "backfill") return
    setBfSourceIdx(0)
    setBfProgress(null)
    setBfError(null)
  }, [panel])

  // ── Automated chunk loop (only while the backfill panel is visible) ─────────
  React.useEffect(() => {
    if (panel !== "backfill") return
    if (!sourcesQ.data?.length) return

    let cancelled = false

    async function run() {
      setBfError(null)
      // Re-read from the query inside the async closure so TypeScript knows the list exists.
      const currentList = sourcesQ.data
      if (!currentList?.length) {
        setUserPanel("gaps")
        return
      }
      const sk = currentList[bfSourceIdx]?.source_key
      if (!sk) {
        setUserPanel("gaps")
        return
      }

      while (!cancelled) {
        let prog: BackfillProgressSnapshot
        try {
          prog = await fetchOnboardingBackfillProgress(sk)
        } catch {
          await new Promise((r) => setTimeout(r, 1000))
          continue
        }
        if (cancelled) return
        setBfProgress(prog)

        if (prog.status === "needs_classification") {
          setClassifySource(sk)
          setUserPanel("classification")
          return
        }

        if (prog.status === "complete") {
          if (bfSourceIdx >= currentList.length - 1) {
            setUserPanel("gaps")
            return
          }
          setBfSourceIdx((i) => i + 1)
          return
        }

        if (prog.status === "paused") {
          return
        }

        if (prog.status === "error") {
          setBfError(
            prog.error_message
              ? getUserFacingErrorMessage(prog.error_message)
              : "We couldn’t import from email for this account. You can go back, check Gmail, and try again.",
          )
          return
        }

        // ``idle`` with nothing queued — prime the first chunk.
        try {
          await postOnboardingBackfillChunk(sk, { chunk_size: 10 })
        } catch (e) {
          if (!cancelled) {
            setBfError(getUserFacingErrorMessage(e) || "We couldn’t start the next batch. Try again.")
          }
          return
        }
        await new Promise((r) => setTimeout(r, 400))
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [panel, bfSourceIdx, bfTick, sourcesQ.data])

  const stepIndex = STEP_META.findIndex((s) => s.id === panel)
  const progressPct = Math.max(5, Math.round(((stepIndex + 1) / STEP_META.length) * 100))

  async function handleResumePause() {
    const sk = activeSourceKey
    if (!sk) return
    setResumeBusy(true)
    setBfError(null)
    try {
      await postOnboardingBackfillResume(sk)
      await postOnboardingBackfillChunk(sk, { resume_from_pause: true, chunk_size: 10 })
      setBfTick((t) => t + 1)
    } catch (e) {
      setBfError(getUserFacingErrorMessage(e) || "We couldn’t resume the import. Try again.")
    } finally {
      setResumeBusy(false)
    }
  }

  function goBack() {
    if (panel === "welcome") {
      onExitFirstStep?.()
      return
    }
    const prevMap: Partial<Record<WizardStepId, WizardStepId>> = {
      summary: "goals",
      goals: "gaps",
      gaps: "apikey",
      apikey: "preclass",
      preclass: "discovery",
      discovery: "welcome",
      backfill: "apikey",
    }
    const prev = prevMap[panel]
    if (prev) setUserPanel(prev)
  }

  const canBack = panel !== "classification" && panel !== "summary"
  const hideChrome = panel === "classification"

  return (
    <div
      className={cn(
        "flex flex-col min-h-[60vh]",
        mode === "setup" && "max-w-4xl mx-auto w-full",
        className,
      )}
    >
      {!hideChrome && (
        <header className="mb-8 space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {mode === "setup" ? "First-run onboarding" : "Connect account"}
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">
            {mode === "setup" ? "Set up Arth" : "Add mail-driven accounts"}
          </h1>
          <div className="h-2 w-full max-w-md rounded-full bg-muted overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <ol className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {STEP_META.map((s, idx) => (
              <li
                key={s.id}
                className={cn(
                  "rounded-full border px-2 py-0.5",
                  idx === stepIndex && "border-primary text-foreground bg-primary/5",
                )}
              >
                {s.label}
              </li>
            ))}
          </ol>
        </header>
      )}

      <div className="flex-1">
        {panel === "welcome" && (
          <StepWelcome onContinue={() => setUserPanel("discovery")} />
        )}
        {panel === "discovery" && (
          <StepDiscovery onContinue={() => setUserPanel("preclass")} />
        )}
        {panel === "preclass" && (
          <div className="space-y-4">
            <PreClassificationForm />
          </div>
        )}
        {panel === "apikey" && (
          <div className="mx-auto w-full max-w-2xl space-y-6">
            <OnboardingOptionalLlmKeys />
          </div>
        )}
        {panel === "backfill" && (
          <div className="space-y-4">
            {sourcesQ.isLoading && (
              <p className="text-sm text-muted-foreground">Loading your email sources…</p>
            )}
            {!sourcesQ.data?.length && !sourcesQ.isLoading && (
              <p className="text-sm text-muted-foreground">
                No bank email sources were found yet. Go back to <strong>Connect Gmail</strong> and
                make sure your inbox is linked, then try <strong>Find accounts</strong> again. If you
                just connected, wait a moment and refresh this page.
              </p>
            )}
            {!!sourcesQ.data?.length && (
              <>
                <StepBackfill
                  title={activeSourceLabel ?? activeSourceKey ?? "…"}
                  progress={bfProgress}
                  error={bfError}
                  onResumeFromPause={bfProgress?.status === "paused" ? handleResumePause : undefined}
                  resumeBusy={resumeBusy}
                />
                <Button type="button" variant="ghost" size="sm" onClick={() => setUserPanel("gaps")}>
                  Skip remaining mail → gap check
                </Button>
              </>
            )}
            {!sourcesQ.data?.length && (
              <Button type="button" variant="secondary" onClick={() => setUserPanel("gaps")}>
                Skip to gap check
              </Button>
            )}
          </div>
        )}
        {panel === "classification" && classifySource && (
          <StepClassification
            source={classifySource}
            sourceLabel={humanizeSourceKey(classifySource)}
            onContinueBackfill={() => {
              setUserPanel("backfill")
              setBfTick((t) => t + 1)
            }}
          />
        )}
        {panel === "gaps" && <StepGapDetection />}
        {panel === "goals" && <GoalTemplateWizard />}
        {panel === "summary" && <StepSummary onDone={onFinished} />}
      </div>

      {!hideChrome && panel !== "welcome" && panel !== "discovery" && (
        <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t pt-6">
          <Button type="button" variant="ghost" onClick={() => goBack()} disabled={!canBack}>
            Back
          </Button>
          <div className="flex flex-wrap gap-2">
            {panel === "preclass" && (
              <Button type="button" onClick={() => setUserPanel("apikey")}>
                Continue
              </Button>
            )}
            {panel === "apikey" && (
              <Button type="button" onClick={() => setUserPanel("backfill")}>
                Start importing mail
              </Button>
            )}
            {panel === "gaps" && (
              <Button type="button" onClick={() => setUserPanel("goals")}>
                Continue to goals
              </Button>
            )}
            {panel === "goals" && (
              <Button type="button" onClick={() => setUserPanel("summary")}>
                Continue
              </Button>
            )}
          </div>
        </footer>
      )}

      {(panel === "welcome" || panel === "discovery") && (
        <footer className="mt-8 flex justify-start">
          <Button
            type="button"
            variant="ghost"
            onClick={() => goBack()}
            disabled={panel === "welcome" && !onExitFirstStep}
          >
            Back
          </Button>
        </footer>
      )}
    </div>
  )
}
