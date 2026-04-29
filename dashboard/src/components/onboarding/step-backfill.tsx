"use client"

/**
 * Step — **chunk backfill progress** (Track 2 Phase 5a).
 *
 * The *parent* wizard owns the polling / ``POST /backfill/{source}`` loop; this file
 * is only responsible for rendering numbers humans care about (emails processed,
 * transactions parsed, unknown backlog).  Keeps the UI reusable from Settings.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"

export type BackfillProgressSnapshot = {
  source: string
  status: string
  emails_found: number
  emails_processed: number
  transactions_parsed: number
  unknowns_pending: number
  error_message: string | null
}

export type StepBackfillProps = {
  /** Human-readable label (usually the pipeline ``source_key``). */
  title: string
  progress: BackfillProgressSnapshot | null
  error: string | null
  /** Shown when the orchestrator reports ``paused`` — calls resume endpoint + chunk. */
  onResumeFromPause?: () => void
  resumeBusy?: boolean
}

/** Map orchestrator status strings to short, user-facing labels. */
function statusLabel(status: string | undefined): string {
  switch (status) {
    case "idle":
      return "Getting ready"
    case "processing":
      return "Working through your mail"
    case "needs_classification":
      return "Waiting for your review"
    case "paused":
      return "Paused"
    case "complete":
      return "Finished this account"
    case "error":
      return "Something went wrong"
    default:
      return status ? status.replace(/_/g, " ") : "Starting…"
  }
}

export function StepBackfill({
  title,
  progress,
  error,
  onResumeFromPause,
  resumeBusy,
}: StepBackfillProps) {
  const pct =
    progress && progress.emails_found > 0
      ? Math.min(100, Math.round((100 * progress.emails_processed) / progress.emails_found))
      : 0

  return (
    <div className="max-w-xl space-y-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Import from email</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Reading bank alert emails for{" "}
          <span className="font-medium text-foreground">{title}</span>. This can take a few minutes —
          we work in small batches so the screen stays responsive.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{statusLabel(progress?.status)}</CardTitle>
          <CardDescription>
            {progress
              ? `${progress.emails_processed} / ${progress.emails_found} messages · ${progress.transactions_parsed} transactions parsed`
              : "Connecting to the API…"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Progress value={pct} className="h-2" />
          {progress && progress.unknowns_pending > 0 && (
            <p className="text-xs text-muted-foreground">
              Transactions still needing your input:{" "}
              <span className="font-medium text-foreground">{progress.unknowns_pending}</span>
            </p>
          )}
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          {progress?.status === "paused" && onResumeFromPause && (
            <Button type="button" variant="secondary" disabled={resumeBusy} onClick={onResumeFromPause}>
              {resumeBusy ? "Resuming…" : "Continue import"}
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
