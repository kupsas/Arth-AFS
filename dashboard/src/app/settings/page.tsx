"use client"

/**
 * Settings — account connection, optional keys, diagnostics, sorting stats.
 * (Statement upload and payment reminders UI are intentionally not shown here.)
 */

import * as React from "react"
import Link from "next/link"
import { useQueryClient } from "@tanstack/react-query"
import { Download, Link2, Tags } from "lucide-react"

import { OnboardingOptionalLlmKeys } from "@/components/onboarding/onboarding-optional-llm-keys"
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard"
import { AgentChatLlmSettings } from "@/components/settings/agent-chat-llm-settings"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { classificationStatsKey, useClassificationStats } from "@/hooks/use-classification-stats"
import {
  onboardingBackfillSourcesKey,
  onboardingStateKey,
} from "@/hooks/use-onboarding"
import { ApiError, downloadDiagnosticsLogsArchive } from "@/lib/api"
import { isDemoMode } from "@/lib/demo"
import { cn } from "@/lib/utils"

export default function SettingsPage() {
  const queryClient = useQueryClient()
  /** Gmail / backfill wizard launched from **Connect account** (Track 2 Phase 5c). */
  const [connectOpen, setConnectOpen] = React.useState(false)
  /** User tapped “Download logs” — show spinner until the ZIP save completes or fails. */
  const [logDownloadPending, setLogDownloadPending] = React.useState(false)
  /** Set when the diagnostics download fails so we show a calm inline message (no toast lib yet). */
  const [logDownloadError, setLogDownloadError] = React.useState<string | null>(null)
  const classificationStats = useClassificationStats()

  return (
    <>
      {isDemoMode && (
        <div className="mb-6 max-w-2xl rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-950 dark:text-amber-50">
          <strong>View-only in the demo.</strong>
        </div>
      )}
      <fieldset
        disabled={isDemoMode}
        className="min-w-0 border-0 p-0 m-0 disabled:opacity-[0.72] disabled:[&_button]:pointer-events-none disabled:[&_input]:pointer-events-none disabled:[&_textarea]:pointer-events-none disabled:[&_select]:pointer-events-none"
      >
        <div className="max-w-2xl flex flex-col gap-8">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Connect account</CardTitle>
              <p className="text-sm text-muted-foreground font-normal">
                Same guided flow as first-time setup — link Gmail, pull in history, and wrap up any
                quick reviews. Start here if you want to import an uploaded bank statement too.
              </p>
            </CardHeader>
            <CardContent>
              <Button type="button" variant="secondary" className="gap-2" onClick={() => setConnectOpen(true)}>
                <Link2 className="size-4" aria-hidden />
                Connect account
              </Button>
            </CardContent>
          </Card>

          <Sheet open={connectOpen} onOpenChange={setConnectOpen}>
            <SheetContent className="w-full sm:max-w-3xl overflow-y-auto flex flex-col">
              <SheetHeader>
                <SheetTitle>Connect account</SheetTitle>
                <SheetDescription>
                  Uses your existing sign-in. When you tap <strong>Finish</strong> at the end, we refresh
                  your numbers on the dashboard.
                </SheetDescription>
              </SheetHeader>
              <div className="flex-1 overflow-y-auto pr-1 pt-2">
                <OnboardingWizard
                  mode="settings"
                  onFinished={() => {
                    setConnectOpen(false)
                    void queryClient.invalidateQueries({ queryKey: ["transactions"] })
                    void queryClient.invalidateQueries({ queryKey: [...classificationStatsKey] })
                    void queryClient.invalidateQueries({ queryKey: [...onboardingStateKey] })
                    void queryClient.invalidateQueries({ queryKey: [...onboardingBackfillSourcesKey] })
                  }}
                />
              </div>
            </SheetContent>
          </Sheet>

          <OnboardingOptionalLlmKeys />

          <AgentChatLlmSettings />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">If something&apos;s off</CardTitle>
              <p className="text-sm text-muted-foreground font-normal">
                If you&apos;re talking to support and they ask for logs, download this — it&apos;s a
                small zip from this device so they can see what the app was doing.
              </p>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <Button
                type="button"
                variant="secondary"
                className="gap-2 w-fit"
                disabled={logDownloadPending}
                onClick={() => {
                  setLogDownloadError(null)
                  setLogDownloadPending(true)
                  void downloadDiagnosticsLogsArchive()
                    .catch((e: unknown) => {
                      const msg =
                        e instanceof ApiError
                          ? e.message
                          : "Couldn't download logs — check that Arth is running, then try again."
                      setLogDownloadError(msg)
                    })
                    .finally(() => setLogDownloadPending(false))
                }}
              >
                <Download className="size-4" aria-hidden />
                {logDownloadPending ? "Preparing…" : "Download logs"}
              </Button>
              {logDownloadError && (
                <p className="text-sm text-destructive" role="alert">
                  {logDownloadError}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Sorting mix</CardTitle>
              <p className="text-sm text-muted-foreground font-normal">
                How your transactions were labelled: built-in rules, smart auto-labels, your
                own fixes, and what&apos;s still open.
              </p>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              {classificationStats.isLoading && (
                <p className="text-muted-foreground">Loading stats…</p>
              )}
              {classificationStats.isError && (
                <p className="text-destructive" role="alert">
                  Couldn&apos;t load your sorting stats. Try refreshing?
                </p>
              )}
              {classificationStats.data && classificationStats.data.total_transactions === 0 && (
                <p className="text-muted-foreground">No transactions in your database yet.</p>
              )}
              {classificationStats.data && classificationStats.data.total_transactions > 0 && (
                <ul className="space-y-1.5 list-none pl-0">
                  <li>
                    <span className="text-muted-foreground">Built-in rules</span>{" "}
                    <span className="font-medium tabular-nums">{classificationStats.data.rules_pct}%</span>
                  </li>
                  <li>
                    <span className="text-muted-foreground">Smart labels</span>{" "}
                    <span className="font-medium tabular-nums">{classificationStats.data.llm_pct}%</span>
                  </li>
                  <li>
                    <span className="text-muted-foreground">Your corrections</span>{" "}
                    <span className="font-medium tabular-nums">
                      {classificationStats.data.user_confirmed_pct}%
                    </span>
                  </li>
                  <li>
                    <span className="text-muted-foreground">Still open</span>{" "}
                    <span className="font-medium tabular-nums">
                      {classificationStats.data.unclassified_pct}%
                    </span>
                  </li>
                  {classificationStats.data.other_pct > 0 && (
                    <li>
                      <span className="text-muted-foreground">Other</span>{" "}
                      <span className="font-medium tabular-nums">{classificationStats.data.other_pct}%</span>
                    </li>
                  )}
                  <li className="text-xs text-muted-foreground pt-2">
                    Based on {classificationStats.data.total_transactions.toLocaleString("en-IN")} total rows.
                  </li>
                </ul>
              )}
              {/* Same destination as the old sidebar link — full sorting-rules UI lives on its own route.
                  Styled Link (not Button asChild): Base UI Button forwards `asChild` onto children,
                  and Next.js Link passes unknown props to `<a>`, which triggers a React warning. */}
              <div className="mt-4 border-t border-border pt-4">
                <Link
                  href="/classification-rules"
                  className={cn(
                    buttonVariants({ variant: "secondary", size: "default" }),
                    "gap-2 w-full sm:w-auto",
                  )}
                >
                  <Tags className="size-4" aria-hidden />
                  Sorting rules
                </Link>
                <p className="mt-2 text-xs text-muted-foreground">
                  Open the screen where you edit how transactions get categories and labels — built-in
                  rules, smart labels, and your own tweaks.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </fieldset>
    </>
  )
}
