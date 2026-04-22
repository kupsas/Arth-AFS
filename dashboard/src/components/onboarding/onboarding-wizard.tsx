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
import { useOnboardingBackfillSources } from "@/hooks/use-onboarding"

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
  { id: "discovery", label: "Discover" },
  { id: "preclass", label: "Identity" },
  { id: "apikey", label: "LLM (opt.)" },
  { id: "backfill", label: "Backfill" },
  { id: "classification", label: "Classify" },
  { id: "gaps", label: "Gaps" },
  { id: "goals", label: "Goals" },
  { id: "summary", label: "Done" },
]

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
  const [panel, setPanel] = React.useState<WizardStepId>("welcome")
  const sourcesQ = useOnboardingBackfillSources()
  const prevPanelRef = React.useRef<WizardStepId | null>(null)

  const [bfSourceIdx, setBfSourceIdx] = React.useState(0)
  const [bfTick, setBfTick] = React.useState(0)
  const [bfProgress, setBfProgress] = React.useState<BackfillProgressSnapshot | null>(null)
  const [bfError, setBfError] = React.useState<string | null>(null)
  const [classifySource, setClassifySource] = React.useState<string | null>(null)
  const [resumeBusy, setResumeBusy] = React.useState(false)

  const activeSourceKey = sourcesQ.data?.[bfSourceIdx]?.source_key ?? null

  // Persist coarse wizard position so a refresh mid-flow still shows the same step name.
  React.useEffect(() => {
    void patchOnboardingState({ current_step: panel }).catch(() => {
      /* non-fatal */
    })
  }, [panel])

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
    const list = sourcesQ.data
    if (!list?.length) return

    let cancelled = false

    async function run() {
      setBfError(null)
      const sk = list[bfSourceIdx]?.source_key
      if (!sk) {
        setPanel("gaps")
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
          setPanel("classification")
          return
        }

        if (prog.status === "complete") {
          if (bfSourceIdx >= list.length - 1) {
            setPanel("gaps")
            return
          }
          setBfSourceIdx((i) => i + 1)
          return
        }

        if (prog.status === "paused") {
          return
        }

        if (prog.status === "error") {
          setBfError(prog.error_message ?? "Backfill failed")
          return
        }

        // ``idle`` with nothing queued — prime the first chunk.
        try {
          await postOnboardingBackfillChunk(sk, { chunk_size: 10 })
        } catch (e) {
          if (!cancelled) {
            setBfError(e instanceof Error ? e.message : "Chunk request failed")
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
      setBfError(e instanceof Error ? e.message : "Resume failed")
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
    if (prev) setPanel(prev)
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
          <StepWelcome onContinue={() => setPanel("discovery")} />
        )}
        {panel === "discovery" && (
          <StepDiscovery onContinue={() => setPanel("preclass")} />
        )}
        {panel === "preclass" && (
          <div className="space-y-4">
            <PreClassificationForm />
          </div>
        )}
        {panel === "apikey" && (
          <div className="space-y-4">
            <OnboardingOptionalLlmKeys />
          </div>
        )}
        {panel === "backfill" && (
          <div className="space-y-4">
            {sourcesQ.isLoading && (
              <p className="text-sm text-muted-foreground">Loading configured sources…</p>
            )}
            {!sourcesQ.data?.length && !sourcesQ.isLoading && (
              <p className="text-sm text-muted-foreground">
                No pipeline sources are configured yet — add bank sender mappings (or use the
                seeded defaults) then re-open this wizard.
              </p>
            )}
            {!!sourcesQ.data?.length && (
              <>
                <StepBackfill
                  title={activeSourceKey ?? "…"}
                  progress={bfProgress}
                  error={bfError}
                  onResumeFromPause={bfProgress?.status === "paused" ? handleResumePause : undefined}
                  resumeBusy={resumeBusy}
                />
                <Button type="button" variant="ghost" size="sm" onClick={() => setPanel("gaps")}>
                  Skip remaining mail → gap check
                </Button>
              </>
            )}
            {!sourcesQ.data?.length && (
              <Button type="button" variant="secondary" onClick={() => setPanel("gaps")}>
                Skip to gap check
              </Button>
            )}
          </div>
        )}
        {panel === "classification" && classifySource && (
          <StepClassification
            source={classifySource}
            onContinueBackfill={() => {
              setPanel("backfill")
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
              <Button type="button" onClick={() => setPanel("apikey")}>
                Continue
              </Button>
            )}
            {panel === "apikey" && (
              <Button type="button" onClick={() => setPanel("backfill")}>
                Start backfill
              </Button>
            )}
            {panel === "gaps" && (
              <Button type="button" onClick={() => setPanel("goals")}>
                Continue to goals
              </Button>
            )}
            {panel === "goals" && (
              <Button type="button" onClick={() => setPanel("summary")}>
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
