/**
 * DateRangePicker — controls the time window for all dashboard widgets.
 *
 * Design:
 *   - Four preset buttons (This Month / Last Month / Last 3M / Last 6M) for the
 *     common cases — no popover needed, just click.
 *   - A "Custom" button opens a Popover with a two-month Calendar for arbitrary
 *     start/end selection.
 *
 * The parent page holds the active preset + derived DateRange in state.
 * This component just renders the UI and calls onPresetChange / onCustomChange.
 *
 * Why separate presets from the DateRange?
 *   We need to know the *previous* period for the MoM delta on summary cards.
 *   Deriving the previous period from a preset is easy; from an arbitrary
 *   DateRange it requires date arithmetic that's easy to get wrong.
 */

"use client"

import * as React from "react"
import { CalendarIcon } from "lucide-react"
import type { DateRange as DayPickerRange } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type { DateRange } from "@/lib/types"

// ─────────────────────────────────────────────────────────────────────────────
// Preset helpers (exported so page.tsx can use them for previous-period calcs)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * "all" = no date filter (all-time view).
 * Used by the Transactions page when the user deselects a preset pill.
 * The dashboard never uses "all" — it always has a date range.
 */
export type Preset = "all" | "this-month" | "last-month" | "last-3m" | "last-6m" | "custom"

export const PRESETS: { id: Preset; label: string }[] = [
  { id: "this-month",  label: "This Month"    },
  { id: "last-month",  label: "Last Month"    },
  { id: "last-3m",     label: "Last 3 Months" },
  { id: "last-6m",     label: "Last 6 Months" },
]

/** ISO "YYYY-MM-DD" string from a Date object */
function toISO(d: Date): string {
  return d.toISOString().split("T")[0]
}

/** The date range for a given preset (always re-computed from today). */
export function getPresetRange(preset: Preset): DateRange {
  const now = new Date()
  switch (preset) {
    case "all":
      // No date filter — returns empty DateRange so the API returns all records
      return {}
    case "this-month":
      return {
        date_from: toISO(new Date(now.getFullYear(), now.getMonth(), 1)),
        date_to:   toISO(now),
      }
    case "last-month": {
      const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
      const end   = new Date(now.getFullYear(), now.getMonth(), 0)      // last day of prev month
      return { date_from: toISO(start), date_to: toISO(end) }
    }
    case "last-3m": {
      const start = new Date(now.getFullYear(), now.getMonth() - 3, 1)
      return { date_from: toISO(start), date_to: toISO(now) }
    }
    case "last-6m": {
      const start = new Date(now.getFullYear(), now.getMonth() - 6, 1)
      return { date_from: toISO(start), date_to: toISO(now) }
    }
    default:
      return {}
  }
}

/**
 * The period *before* the one described by the preset.
 * Used by SummaryCards to compute the month-over-month delta.
 *
 * Examples:
 *   this-month  → same calendar month, one month back
 *   last-month  → the month before last month
 *   last-3m     → the three months before the current last-3m window
 *   last-6m     → the six months before the current last-6m window
 */
export function getPreviousRange(preset: Preset): DateRange {
  if (preset === "all") return {}   // no concept of "previous" when all-time
  const now = new Date()
  switch (preset) {
    case "this-month": {
      // previous period = last full month
      const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
      const end   = new Date(now.getFullYear(), now.getMonth(), 0)
      return { date_from: toISO(start), date_to: toISO(end) }
    }
    case "last-month": {
      // previous period = two months ago (full month)
      const start = new Date(now.getFullYear(), now.getMonth() - 2, 1)
      const end   = new Date(now.getFullYear(), now.getMonth() - 1, 0)
      return { date_from: toISO(start), date_to: toISO(end) }
    }
    case "last-3m": {
      // previous period = the 3 months before the current window
      const start = new Date(now.getFullYear(), now.getMonth() - 6, 1)
      const end   = new Date(now.getFullYear(), now.getMonth() - 3, 0)
      return { date_from: toISO(start), date_to: toISO(end) }
    }
    case "last-6m": {
      // previous period = the 6 months before the current window
      const start = new Date(now.getFullYear(), now.getMonth() - 12, 1)
      const end   = new Date(now.getFullYear(), now.getMonth() - 6, 0)
      return { date_from: toISO(start), date_to: toISO(end) }
    }
    default:
      return {}
  }
}

/** Human-readable label for a DateRange (shown on the custom button). */
function formatRange(range: DateRange): string {
  if (!range.date_from || !range.date_to) return "Custom"
  const fmt = (iso: string) =>
    new Date(iso + "T00:00:00").toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
    })
  return `${fmt(range.date_from)} – ${fmt(range.date_to)}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

interface DateRangePickerProps {
  preset: Preset
  customRange: DateRange     // only relevant when preset === "custom"
  onPresetChange: (preset: Preset, range: DateRange) => void
  onCustomChange: (range: DateRange) => void
  /**
   * When true, clicking an already-active preset button deselects it,
   * setting the preset to "all" (no date filter). Used on the Transactions
   * page so the user can clear the date filter by clicking the active pill.
   */
  clearable?: boolean
  className?: string
}

export function DateRangePicker({
  preset,
  customRange,
  onPresetChange,
  onCustomChange,
  clearable = false,
  className,
}: DateRangePickerProps) {
  // Internal DayPicker range state for the custom calendar
  const [calRange, setCalRange] = React.useState<DayPickerRange | undefined>(
    customRange.date_from && customRange.date_to
      ? {
          from: new Date(customRange.date_from + "T00:00:00"),
          to:   new Date(customRange.date_to   + "T00:00:00"),
        }
      : undefined
  )
  const [open, setOpen] = React.useState(false)

  function handleCalendarSelect(range: DayPickerRange | undefined) {
    setCalRange(range)
    if (range?.from && range?.to) {
      const newRange: DateRange = {
        date_from: toISO(range.from),
        date_to:   toISO(range.to),
      }
      onCustomChange(newRange)
      setOpen(false)
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {/* Preset quick-select buttons.
          When clearable, clicking an active button deselects it (→ "all"). */}
      {PRESETS.map((p) => (
        <Button
          key={p.id}
          variant={preset === p.id ? "default" : "outline"}
          size="sm"
          onClick={() => {
            if (clearable && preset === p.id) {
              // Deselect: clear the date filter
              onPresetChange("all", {})
            } else {
              onPresetChange(p.id, getPresetRange(p.id))
            }
          }}
          className="h-8 text-xs"
        >
          {p.label}
        </Button>
      ))}

      {/* Custom date range via calendar */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <Button
              variant={preset === "custom" ? "default" : "outline"}
              size="sm"
              className="h-8 gap-1.5 text-xs"
            />
          }
        >
          <CalendarIcon className="size-3.5" />
          {preset === "custom" ? formatRange(customRange) : "Custom"}
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="end">
          <Calendar
            mode="range"
            selected={calRange}
            onSelect={handleCalendarSelect}
            numberOfMonths={2}
            disabled={{ after: new Date() }}
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
