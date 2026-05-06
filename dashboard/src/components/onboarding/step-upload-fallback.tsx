"use client"

/**
 * **Statement upload fallback** during onboarding (Import mail step).
 *
 * Some users never get transaction rows from Gmail (no alerts in inbox, wrong account, etc.).
 * The parent wizard calls ``GET /api/onboarding/has-data`` before moving to Coverage; if the
 * count is zero, we keep the user on this step and highlight this card so they can drop a
 * bank-exported file instead — same pipeline as the dashboard **Upload statement** dialog.
 *
 * While **mail import** is actively writing to the database, the drop zone is disabled so a
 * statement upload does not race the same SQLite session.
 */

import * as React from "react"

import { StatementUploadPanel } from "@/components/dashboard/upload-button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { TRANSACTION_UPLOAD_TYPE_LABELS } from "@/lib/statement-upload-type-labels"
import { cn } from "@/lib/utils"

export type StepUploadFallbackProps = {
  /**
   * When true, the user tried to continue but Arth still has **zero** transactions for them —
   * we bump visual emphasis so the upload path is obvious.
   */
  gateBlocked: boolean
  /**
   * True while Gmail mail import is actively streaming and writing rows — disables statement
   * upload so both paths do not hit SQLite at once.
   */
  mailImportBusy: boolean
  /** Called after a successful statement import (parent refetches has-data and may clear the gate). */
  onImportComplete?: () => void
}

export function StepUploadFallback({
  gateBlocked,
  mailImportBusy,
  onImportComplete,
}: StepUploadFallbackProps) {
  return (
    <Card
      id="onboarding-statement-fallback"
      className={cn(
        "scroll-mt-24 border-dashed transition-[box-shadow,border-color]",
        gateBlocked && "border-amber-500/60 shadow-[0_0_0_1px_rgba(245,158,11,0.25)]",
      )}
    >
      <CardHeader className="space-y-1">
        <CardTitle className="text-lg">
          {gateBlocked
            ? "We still need at least one transaction"
            : "Have a statement file instead?"}
        </CardTitle>
        <CardDescription>
          {gateBlocked ? (
            <>
              Email import didn&apos;t add anything yet. Upload a statement you downloaded from
              net banking — we&apos;ll import it the same way as on the main dashboard.
            </>
          ) : (
            <>
              If your bank doesn&apos;t send useful mail to this inbox, you can skip the wait and
              upload an export (.txt, .csv, or .pdf). We detect the format from the file contents.
            </>
          )}
        </CardDescription>
        <p className="text-xs text-muted-foreground leading-relaxed pt-1">
          <span className="font-medium text-foreground">Supported today:</span>{" "}
          {TRANSACTION_UPLOAD_TYPE_LABELS.join(" · ")}
        </p>
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        {mailImportBusy && (
          <p className="text-sm text-muted-foreground rounded-lg border bg-muted/30 px-3 py-2">
            Finish the email import above first (or wait until it pauses for your review). Then you
            can drop a statement here — that keeps your data import from fighting itself.
          </p>
        )}
        <StatementUploadPanel disabled={mailImportBusy} onImportComplete={onImportComplete} />
      </CardContent>
    </Card>
  )
}
