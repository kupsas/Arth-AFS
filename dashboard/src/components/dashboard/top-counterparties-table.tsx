/**
 * TopCounterpartiesTable — compact table showing the top N merchants / payees
 * by total spend in the selected date range.
 *
 * Columns: rank · counterparty · category · amount · txn count
 *
 * Design notes:
 *   - Rank column uses a subtle number badge for quick scanning
 *   - Category is shown as a small coloured dot + label (not a full Badge
 *     component, which would be too tall for a compact table row)
 *   - Amount right-aligned in a monospaced font for easy comparison
 *   - No pagination — just top 10; user goes to Transactions page for more
 */

"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useTopCounterparties } from "@/hooks/use-metrics"
import { categoryHexColor, formatCurrency, cn } from "@/lib/utils"
import type { DateRange } from "@/lib/types"

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

interface TopCounterpartiesTableProps {
  dateRange: DateRange
  limit?: number
  className?: string
}

export function TopCounterpartiesTable({
  dateRange,
  limit = 10,
  className,
}: TopCounterpartiesTableProps) {
  const { data, isLoading, isError } = useTopCounterparties(dateRange, limit)

  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader>
        <CardTitle className="text-base">Top Counterparties</CardTitle>
      </CardHeader>

      <CardContent className="flex-1 px-0">
        {isLoading && (
          <div className="flex flex-col gap-2 px-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-5 w-5 rounded-full" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-4 w-16" />
              </div>
            ))}
          </div>
        )}

        {isError && (
          <p className="px-4 py-2 text-sm text-muted-foreground">
            Failed to load data.
          </p>
        )}

        {!isLoading && !isError && (!data || data.length === 0) && (
          <p className="px-4 py-2 text-sm text-muted-foreground">
            No transactions in this period.
          </p>
        )}

        {!isLoading && !isError && data && data.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-2 pl-4 pr-2 text-center font-medium">#</th>
                <th className="py-2 pr-3 text-left font-medium">Counterparty</th>
                <th className="hidden py-2 pr-3 text-left font-medium sm:table-cell">
                  Category
                </th>
                <th className="py-2 pr-4 text-right font-medium">Amount</th>
                <th className="hidden py-2 pr-4 text-right font-medium lg:table-cell">
                  Txns
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, index) => {
                const cat = row.category ?? "Unclassified"
                const color = categoryHexColor(cat)

                return (
                  <tr
                    key={`${row.counterparty ?? "unknown"}-${index}`}
                    className="border-b border-border/50 transition-colors last:border-0 hover:bg-muted/40"
                  >
                    {/* Rank */}
                    <td className="py-2.5 pl-4 pr-2 text-center">
                      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
                        {index + 1}
                      </span>
                    </td>

                    {/* Counterparty name */}
                    <td className="py-2.5 pr-3">
                      <span className="font-medium leading-tight">
                        {row.counterparty ?? (
                          <span className="italic text-muted-foreground">Unknown</span>
                        )}
                      </span>
                    </td>

                    {/* Category dot + label (hidden on xs) */}
                    <td className="hidden py-2.5 pr-3 sm:table-cell">
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <span
                          className="inline-block h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        {cat}
                      </span>
                    </td>

                    {/* Amount */}
                    <td className="py-2.5 pr-4 text-right">
                      <span className="font-mono font-medium tabular-nums">
                        {formatCurrency(row.amount)}
                      </span>
                    </td>

                    {/* Txn count (hidden on md and below) */}
                    <td className="hidden py-2.5 pr-4 text-right text-xs text-muted-foreground lg:table-cell">
                      {row.txn_count}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  )
}
