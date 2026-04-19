"use client";

/**
 * Shown while the agent is still working (submitted, not yet ``done``).
 * When the server streams ``tool_call_*`` events, we list each tool name
 * (read-only labels) so the wait feels informative — like Cursor’s step log.
 */

import type { LiveTool } from "@/lib/chat-types";
import { cn } from "@/lib/utils";

/** Turn ``get_spending_by_category`` into a short human-ish label for the strip. */
function formatToolLabel(rawName: string): string {
  const s = rawName.trim();
  if (!s) return "tool";
  return s
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .split(" ")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function StreamingIndicator({
  className,
  liveTools,
}: {
  className?: string;
  /** Tool names emitted over the socket during this turn (running → done). */
  liveTools?: LiveTool[];
}) {
  const tools = liveTools ?? [];

  return (
    <div
      className={cn("flex flex-col gap-2 text-xs text-muted-foreground", className)}
      aria-live="polite"
    >
      <div className="flex items-center gap-1.5">
        <span className="inline-flex gap-0.5">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/80 [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/80 [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/80" />
        </span>
        <span>Arth is thinking…</span>
      </div>

      {tools.length > 0 && (
        <ul className="ml-0 flex list-none flex-col gap-1 border-l border-border pl-3">
          {tools.map((t, i) => (
            <li key={`${t.name}-${i}`} className="flex items-center gap-2">
              {t.status === "done" ? (
                <span
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground"
                  aria-hidden
                >
                  ✓
                </span>
              ) : (
                <span
                  className="relative flex h-4 w-4 shrink-0 items-center justify-center"
                  aria-hidden
                >
                  <span className="absolute inset-0 animate-pulse rounded-full bg-primary/25" />
                  <span className="relative h-2 w-2 rounded-full bg-primary/80" />
                </span>
              )}
              <span
                className={
                  t.status === "done"
                    ? "text-muted-foreground/70"
                    : "font-medium text-foreground"
                }
              >
                {formatToolLabel(t.name)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
