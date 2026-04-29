"use client"

/**
 * Final wizard panel — **mark onboarding complete** (Track 2 Phase 5a).
 *
 * ``POST /api/onboarding/complete`` also mirrors the legacy ``setup_completed`` flag
 * when this is the user’s first run, so the dashboard shell unlocks after navigation.
 */

import * as React from "react"
import { PartyPopper } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useOnboardingComplete } from "@/hooks/use-onboarding"
import { getUserFacingErrorMessage } from "@/lib/user-facing-api-error"

export type StepSummaryProps = {
  onDone: () => void
}

export function StepSummary({ onDone }: StepSummaryProps) {
  const complete = useOnboardingComplete()
  const [err, setErr] = React.useState<string | null>(null)

  async function finish() {
    setErr(null)
    try {
      await complete.mutateAsync()
      onDone()
    } catch (e) {
      setErr(getUserFacingErrorMessage(e) || "We couldn’t save your progress. Try again.")
    }
  }

  return (
    <Card className="max-w-lg border-emerald-500/30">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <PartyPopper className="size-6 text-emerald-600" aria-hidden />
          You are ready
        </CardTitle>
        <CardDescription>
          Your email import is set up, you can add PDF statements any time if you spot gaps, and you
          can open the main <strong>Goals</strong> tab whenever you want to adjust targets.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {err && (
          <p className="text-sm text-destructive" role="alert">
            {err}
          </p>
        )}
        <Button className="w-full" size="lg" disabled={complete.isPending} onClick={() => void finish()}>
          {complete.isPending ? "Saving…" : "Finish and open dashboard"}
        </Button>
      </CardContent>
    </Card>
  )
}
