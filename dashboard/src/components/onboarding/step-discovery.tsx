"use client"

/**
 * Step 2 — Auto-discovery (Track 2 Phase 5a).
 *
 * Calls ``POST /api/onboarding/discover`` for cheap Gmail searches per bank sender.
 * Errors are shown with human copy (never raw JSON from the API).
 */

import * as React from "react"
import { Loader2, Radar } from "lucide-react"

import { OnboardingErrorCallout } from "@/components/onboarding/onboarding-error-callout"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useOnboardingDiscover } from "@/hooks/use-onboarding"
import { getUserFacingErrorMessage } from "@/lib/user-facing-api-error"

type DiscoveryRow = {
  sender_email: string
  display_name: string
  source_type: string
  email_count_estimate: number
  earliest_email_date: string | null
  latest_email_date: string | null
}

export type StepDiscoveryProps = {
  onContinue: () => void
}

export function StepDiscovery({ onContinue }: StepDiscoveryProps) {
  const discover = useOnboardingDiscover()
  const [rows, setRows] = React.useState<DiscoveryRow[] | null>(null)

  async function run() {
    try {
      const data = (await discover.mutateAsync()) as {
        sources?: DiscoveryRow[]
      }
      setRows(data.sources ?? [])
    } catch {
      // Do not show an empty “accounts” table next to a failure — keep table hidden until a good run.
      setRows(null)
    }
  }

  React.useEffect(() => {
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  const errorText = discover.isError ? getUserFacingErrorMessage(discover.error) : null
  const canContinue =
    !discover.isPending && !discover.isError && rows !== null

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center gap-2">
        <Radar className="size-7 text-primary" aria-hidden />
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Discover sources</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            We scan your mailbox for known bank sender addresses. In this step we only read email
            headers and search metadata — not full message bodies.
          </p>
        </div>
      </div>

      {discover.isPending && (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" />
          Connecting to Gmail…
        </p>
      )}

      {errorText && (
        <OnboardingErrorCallout
          title="We couldn’t finish this step"
          hint='Use the “Back” button at the bottom to return to “Connect Gmail,” sign in with Google, then come back here and tap “Re-scan.”'
        >
          {errorText}
        </OnboardingErrorCallout>
      )}

      {rows && !discover.isError && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Accounts we found</CardTitle>
            <CardDescription>
              Approximate email counts help you spot a missing bank before we import a long history.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Sender</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">≈ Msgs</TableHead>
                  <TableHead>Date span</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.sender_email}>
                    <TableCell>
                      <div className="font-medium">{r.display_name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{r.sender_email}</div>
                    </TableCell>
                    <TableCell className="capitalize">{r.source_type}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.email_count_estimate}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {r.earliest_email_date ?? "—"} → {r.latest_email_date ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => void run()} disabled={discover.isPending}>
          Re-scan
        </Button>
        <Button type="button" onClick={() => onContinue()} disabled={!canContinue}>
          Continue
        </Button>
      </div>
    </div>
  )
}
