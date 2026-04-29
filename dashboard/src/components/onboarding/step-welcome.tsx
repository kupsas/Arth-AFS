"use client"

/**
 * Step 1 — Welcome + connect Gmail (Track 2 Phase 5a).
 *
 * Gmail tokens live on your machine with the API; this button starts the same
 * browser sign-in flow as before. After Google finishes, return here and tap continue.
 */

import * as React from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { buildApiUrl } from "@/lib/api-base"
import { userMessageFromApiResponseBody } from "@/lib/user-facing-api-error"

export type StepWelcomeProps = {
  /** Fires once the user confirms Gmail is connected (they clicked Continue). */
  onContinue: () => void
}

export function StepWelcome({ onContinue }: StepWelcomeProps) {
  const [error, setError] = React.useState<string | null>(null)
  const [busyConnect, setBusyConnect] = React.useState(false)
  const [busyContinue, setBusyContinue] = React.useState(false)

  async function startOAuth() {
    setError(null)
    setBusyConnect(true)
    try {
      const res = await fetch(buildApiUrl("/api/scraper/oauth/init"), {
        method: "POST",
        credentials: "include",
      })
      const t = await res.text()
      if (!res.ok) {
        // FastAPI may return { detail: ... } — userMessageFromApiResponseBody flattens it
        setError(userMessageFromApiResponseBody(t) || "Could not start sign-in. Try again.")
        return
      }
    } catch {
      setError("We could not reach Arth. Make sure the app is running, then try again.")
    } finally {
      setBusyConnect(false)
    }
  }

  async function continueIfConnected() {
    setError(null)
    setBusyContinue(true)
    try {
      const res = await fetch(buildApiUrl("/api/scraper/oauth/status"), {
        credentials: "include",
      })
      const t = await res.text()
      if (!res.ok) {
        setError(
          userMessageFromApiResponseBody(t) ||
            "We could not confirm your Gmail connection. Please try again.",
        )
        return
      }

      const payload = (JSON.parse(t || "{}") ?? {}) as {
        is_authenticated?: boolean
      }
      if (!payload.is_authenticated) {
        setError(
          "Gmail is not connected yet. Click “Connect Gmail”, finish the Google sign-in in your browser, then tap continue.",
        )
        return
      }

      onContinue()
    } catch {
      setError("We could not check Gmail right now. Please try again.")
    } finally {
      setBusyContinue(false)
    }
  }

  return (
    <Card className="max-w-lg border-muted">
      <CardHeader>
        <CardTitle>Connect Gmail</CardTitle>
        <CardDescription>
          Arth reads <strong>bank alert emails</strong> you already get (HDFC, ICICI, etc.) to build
          your ledger. Your data stays on this computer — we do not send your mail to analytics
          services. Use the button below to sign in with Google in your browser, then come back
          here.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <Button
          type="button"
          className="w-full"
          disabled={busyConnect || busyContinue}
          onClick={() => void startOAuth()}
        >
          {busyConnect ? "Starting…" : "Connect Gmail"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Complete the Google sign-in window, then return to this page.
        </p>
        <Button
          type="button"
          variant="secondary"
          className="w-full"
          disabled={busyConnect || busyContinue}
          onClick={() => void continueIfConnected()}
        >
          {busyContinue ? "Checking Gmail…" : "I already connected Gmail — continue"}
        </Button>
      </CardContent>
    </Card>
  )
}
