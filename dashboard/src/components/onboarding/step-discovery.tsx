"use client"

/**
 * Step 2 — **Auto-discovery** (Track 2 Phase 5a).
 *
 * Calls ``POST /api/onboarding/discover`` which does cheap Gmail searches per
 * configured bank sender.  Results are persisted server-side; we also show a
 * friendly table so the user sees what was found before moving on.
 */

import * as React from "react"
import { Loader2, Radar } from "lucide-react"

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
      setRows([])
    }
  }

  React.useEffect(() => {
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, [])

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center gap-2">
        <Radar className="size-7 text-primary" aria-hidden />
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Discover sources</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Scanning your mailbox for known bank sender addresses (no email bodies are downloaded
            in this pass).
          </p>
        </div>
      </div>

      {discover.isPending && (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="size-4 animate-spin" />
          Talking to Gmail…
        </p>
      )}

      {discover.isError && (
        <Card className="border-destructive/50">
          <CardContent className="pt-6 text-sm text-destructive">
            {(discover.error as Error)?.message ?? "Discovery failed — check Gmail auth."}
          </CardContent>
        </Card>
      )}

      {rows && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Configured senders</CardTitle>
            <CardDescription>
              Rough message counts help you spot a missing bank domain before a long backfill.
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
        <Button type="button" onClick={() => onContinue()} disabled={discover.isPending || rows === null}>
          Continue
        </Button>
      </div>
    </div>
  )
}
