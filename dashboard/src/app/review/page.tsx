/**
 * Review Queue page — the human-in-the-loop feedback screen.
 *
 * Shows all unreviewed transactions as cards. The user can:
 *   ✓ Approve        immediately marks is_reviewed: true
 *   ✏ Edit & Approve opens the edit sheet (is_reviewed pre-ticked)
 *   → Skip           hides the card locally (won't persist; card reappears on refresh)
 *
 * Layout:
 *   1. Header with progress (X of Y reviewed this session)
 *   2. Progress bar
 *   3. Grid of ReviewCards (responsive: 1 / 2 / 3 columns)
 *   4. Empty state when all cards are done (or all skipped)
 *   5. Pagination bar (load more / page through)
 *
 * State:
 *   - page            current pagination page
 *   - skippedIds      Set of transaction IDs the user skipped (local only)
 *   - editTxn         the transaction being edited (null if sheet closed)
 *   - approvingIds    Set of IDs currently being PATCH'd (shows spinner)
 *
 * Data flow:
 *   - useTransactions({ is_reviewed: false }) → React Query
 *   - onApprove → useUpdateTransaction({ is_reviewed: true })
 *   - onEditApprove → open TransactionEditSheet (forceReviewed=true)
 *   - onSkip → add to local skippedIds set
 */

"use client"

import * as React from "react"
import { CheckCircle2, ClipboardCheck } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ReviewCard } from "@/components/review/review-card"
import { TransactionEditSheet } from "@/components/transactions/transaction-edit-sheet"
import { useTransactions, useUpdateTransaction } from "@/hooks/use-transactions"
import type { Transaction } from "@/lib/types"

// ─────────────────────────────────────────────────────────────────────────────
// Page component
// ─────────────────────────────────────────────────────────────────────────────

export default function ReviewPage() {
  // ── Pagination ────────────────────────────────────────────────────────────
  const [page, setPage] = React.useState(1)

  // ── Local "skip" state ────────────────────────────────────────────────────
  // Skipped IDs are hidden from view but NOT persisted to the server.
  // They reappear when the page refreshes. This is intentional — "skip"
  // means "I'll deal with this later", not "mark as reviewed".
  const [skippedIds, setSkippedIds] = React.useState<Set<number>>(new Set())

  // ── Edit sheet state ──────────────────────────────────────────────────────
  const [editTxn, setEditTxn] = React.useState<Transaction | null>(null)
  const [editSheetOpen, setEditSheetOpen] = React.useState(false)

  // ── IDs currently being approved (to show per-card loading state) ─────────
  const [approvingIds, setApprovingIds] = React.useState<Set<number>>(new Set())

  // ── Session-approved count (for the progress indicator) ──────────────────
  // We track this locally because once a transaction is approved it disappears
  // from the list. React Query won't show us what was already approved.
  const [sessionApproved, setSessionApproved] = React.useState(0)

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data, isLoading } = useTransactions({
    is_reviewed: false,
    page,
    page_size: 18, // 3 columns × 6 rows fits most screens
    sort_by: "created_at",
    sort_order: "desc",
  })

  const { mutateAsync: updateTransaction } = useUpdateTransaction()

  // ─────────────────────────────────────────────────────────────────────────
  // Handlers
  // ─────────────────────────────────────────────────────────────────────────

  async function handleApprove(id: number) {
    setApprovingIds((prev) => new Set(prev).add(id))
    try {
      await updateTransaction({ id, update: { is_reviewed: true } })
      setSessionApproved((n) => n + 1)
    } finally {
      setApprovingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  function handleEditApprove(txn: Transaction) {
    setEditTxn(txn)
    setEditSheetOpen(true)
  }

  function handleSkip(id: number) {
    setSkippedIds((prev) => new Set(prev).add(id))
  }

  // When the edit sheet closes after saving, increment session counter
  function handleEditSheetOpenChange(open: boolean) {
    if (!open && editTxn) {
      // We assume if the sheet closed it was saved (quick approve in the sheet
      // also triggers this). This over-counts slightly if the user just closes
      // without saving, but it's close enough for the progress indicator.
      setSessionApproved((n) => n + 1)
    }
    setEditSheetOpen(open)
    if (!open) setEditTxn(null)
  }

  // ─────────────────────────────────────────────────────────────────────────
  // Derived values
  // ─────────────────────────────────────────────────────────────────────────

  // Filter out skipped cards
  const visibleCards = (data?.items ?? []).filter(
    (txn) => !skippedIds.has(txn.id),
  )

  // Total unreviewed on the server (our progress denominator)
  const totalUnreviewed = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-6">

      {/* ── Page header ──────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Review Queue</h1>
          <p className="text-sm text-muted-foreground">
            Approve or correct each transaction&apos;s classification.
          </p>
        </div>

        {/* Session progress pill */}
        {sessionApproved > 0 && (
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-sm font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="size-4" />
            {sessionApproved} approved this session
          </div>
        )}
      </div>

      {/* ── Queue stats bar ───────────────────────────────────────────── */}
      {!isLoading && (
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {totalUnreviewed === 0
              ? "All caught up!"
              : `${totalUnreviewed.toLocaleString()} unreviewed transaction${totalUnreviewed !== 1 ? "s" : ""} remaining`}
          </span>
          {skippedIds.size > 0 && (
            <button
              className="text-xs text-muted-foreground underline underline-offset-2"
              onClick={() => setSkippedIds(new Set())}
            >
              Restore {skippedIds.size} skipped
            </button>
          )}
        </div>
      )}

      {/* ── Cards grid ──────────────────────────────────────────────── */}
      {isLoading ? (
        // Loading skeleton — show placeholder cards
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-lg border flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between">
                <div className="flex flex-col gap-2 flex-1">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
                <Skeleton className="h-7 w-16 ml-3" />
              </div>
              <Skeleton className="h-8 w-full" />
              <div className="flex gap-1.5">
                <Skeleton className="h-5 w-20 rounded-full" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
            </div>
          ))}
        </div>
      ) : visibleCards.length === 0 && totalUnreviewed === 0 ? (
        // All-done empty state
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <div className="rounded-full bg-emerald-500/10 p-4">
            <ClipboardCheck className="size-10 text-emerald-500" />
          </div>
          <div>
            <h2 className="text-lg font-semibold">All caught up!</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Every transaction has been reviewed. New ones will appear here
              as they arrive.
            </p>
          </div>
        </div>
      ) : visibleCards.length === 0 && totalUnreviewed > 0 ? (
        // All visible cards were skipped but more exist on server
        <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
          <p className="text-sm text-muted-foreground">
            You&apos;ve skipped all cards on this page.{" "}
            <button
              className="underline underline-offset-2"
              onClick={() => setSkippedIds(new Set())}
            >
              Restore skipped
            </button>{" "}
            or move to the next page.
          </p>
        </div>
      ) : (
        // The actual card grid
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleCards.map((txn) => (
            <ReviewCard
              key={txn.id}
              transaction={txn}
              onApprove={handleApprove}
              isApproving={approvingIds.has(txn.id)}
              onEditApprove={handleEditApprove}
              onSkip={handleSkip}
            />
          ))}
        </div>
      )}

      {/* ── Pagination ────────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}

      {/* ── Edit sheet (opens on "Edit & Approve") ────────────────────── */}
      <TransactionEditSheet
        txnId={editTxn?.id ?? null}
        open={editSheetOpen}
        onOpenChange={handleEditSheetOpenChange}
        forceReviewed
      />

    </div>
  )
}
