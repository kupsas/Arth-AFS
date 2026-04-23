"use client"

/**
 * Step 1 — **Welcome + Gmail OAuth** (Track 2 Phase 5a).
 *
 * Gmail tokens live on the API server; this button simply kicks off the same
 * ``POST /api/scraper/oauth/init`` flow the legacy setup page used.  After OAuth
 * succeeds in the browser, the user returns here and taps **Continue**.
 */

import * as React from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { buildApiUrl } from "@/lib/api-base"

export type StepWelcomeProps = {
  /** Fires once the user confirms Gmail is connected (they clicked Continue). */
  onContinue: () => void
}

export function StepWelcome({ onContinue }: StepWelcomeProps) {
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  async function startOAuth() {
    setError(null)
    setBusy(true)
    try {
      const res = await fetch(buildApiUrl("/api/scraper/oauth/init"), {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string }
        setError(body.detail ?? "OAuth init failed")
        return
      }
    } catch {
      setError("Could not reach the API. Is it running?")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="max-w-lg border-muted">
      <CardHeader>
        <CardTitle>Connect Gmail</CardTitle>
        <CardDescription>
          Arth reads **bank alert emails** you already receive — nothing is sent to a third-party
          analytics service. OAuth runs on your local API; keep{" "}
          <code className="rounded bg-muted px-1 text-xs">data/gmail_credentials.json</code> in
          place.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <Button type="button" className="w-full" disabled={busy} onClick={() => void startOAuth()}>
          {busy ? "Starting…" : "Start Gmail OAuth"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Complete the Google consent screen in your browser, then return here.
        </p>
        <Button type="button" variant="secondary" className="w-full" onClick={() => onContinue()}>
          Continue — Gmail is connected
        </Button>
      </CardContent>
    </Card>
  )
}
