"use client";

/**
 * Collapsible list of tool invocations (name, args, result) for the “thinking” panel.
 *
 * Uses native <details> so we do not add a new shadcn dependency.
 */

import { useState } from "react";
import { ChevronDown, Wrench } from "lucide-react";

import type { ToolCallUi } from "@/lib/chat-types";
import { cn } from "@/lib/utils";

function JsonPreview({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);
  const s = JSON.stringify(data, null, 2);
  const long = s.length > 400;
  const shown = open || !long ? s : `${s.slice(0, 400)}…`;
  return (
    <div>
      <pre
        className={cn(
          "mt-1 max-w-full overflow-x-auto rounded-md bg-muted/50 p-2 text-[0.7rem] leading-relaxed",
          !open && long && "max-h-32 overflow-y-auto",
        )}
      >
        {shown}
      </pre>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="mt-1 text-xs text-primary underline"
        >
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

export function ToolCallGroup({ tools }: { tools: ToolCallUi[] }) {
  if (!tools.length) return null;

  return (
    <details className="group mb-2 rounded-lg border border-border/60 bg-muted/20 text-left text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 font-medium text-foreground">
        <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
        <span>Data Arth looked up</span>
        <ChevronDown className="ml-auto h-4 w-4 text-muted-foreground transition group-open:rotate-180" />
      </summary>
      <div className="space-y-2 border-t border-border/50 px-3 py-2">
        {tools.map((t, i) => (
          <div
            key={`${t.name}-${i}`}
            className="rounded-md border border-border/40 bg-background/50 p-2"
          >
            <div className="font-mono text-xs font-semibold text-primary">
              {t.name}
              {t.duration_ms != null && (
                <span className="ml-2 font-sans text-[0.65rem] font-normal text-muted-foreground">
                  {t.duration_ms} ms
                </span>
              )}
            </div>
            <div className="mt-1 text-[0.65rem] text-muted-foreground">Arguments</div>
            <JsonPreview data={t.arguments} />
            {t.result !== undefined && (
              <>
                <div className="mt-2 text-[0.65rem] text-muted-foreground">Result</div>
                <JsonPreview data={t.result} />
              </>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
