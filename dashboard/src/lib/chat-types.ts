/**
 * Types for dashboard agent chat — REST resources and WebSocket wire protocol.
 * Server shapes come from FastAPI (`api/routes/chat_ws.py`) and `agent/events.py`.
 */

/** GET /api/chat/sessions */
export interface ChatSessionSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

/** GET /api/chat/sessions/{id} */
export interface ChatSessionDetail extends ChatSessionSummary {
  messages: Record<string, unknown>[];
}

/** One tool invocation shown in the “thinking” strip */
export interface ToolCallUi {
  name: string;
  arguments: Record<string, unknown>;
  /** Populated after `tool_call_completed` */
  result?: Record<string, unknown>;
  duration_ms?: number;
}

/** Lightweight row for the live “thinking” strip — tool names only, no arguments. */
export interface LiveTool {
  name: string;
  status: "running" | "done";
}

/** Rendered chat row */
export interface ChatMessageUi {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallUi[];
}

/** Inbound JSON from the WebSocket (subset; ignore unknown `type`s) */
export type ServerChatWireMessage =
  | {
      type: "session_ready";
      session_id: string;
      title: string | null;
    }
  | {
      type: "llm_step";
      step: number;
      model: string | null;
      finish_reason: string | null;
      content: string | null;
      reasoning: string | null;
      tool_intents: { name: string; arguments: Record<string, unknown> }[];
    }
  | {
      type: "tool_call_started";
      tool_name: string;
      arguments: Record<string, unknown>;
      tool_call_id: string | null;
    }
  | {
      type: "tool_call_completed";
      tool_name: string;
      result: Record<string, unknown>;
      duration_ms: number;
      tool_call_id: string | null;
    }
  | { type: "token"; token: string }
  | { type: "response"; content: string }
  | { type: "error"; message: string; recoverable: boolean }
  | {
      type: "screening_blocked";
      category: string;
      message: string;
      layer: string;
      latency_ms: number;
    }
  | { type: "done" };

/** Client → server */
export type ClientChatWireMessage =
  | { type: "send_message"; content: string }
  | { type: "stop" };

function uid(): string {
  return crypto.randomUUID?.() ?? `m-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function tryParseJson(s: unknown): Record<string, unknown> | undefined {
  if (typeof s !== "string") return undefined;
  try {
    const v = JSON.parse(s) as unknown;
    return typeof v === "object" && v !== null && !Array.isArray(v)
      ? (v as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Converts persisted OpenAI-format rows into UI rows (collapses tool messages into the assistant turn).
 */
export function normalizeOpenAiMessagesToUi(
  raw: Record<string, unknown>[],
): ChatMessageUi[] {
  const result: ChatMessageUi[] = [];
  let i = 0;

  while (i < raw.length) {
    const m = raw[i];
    const role = String(m.role ?? "");

    if (role === "user") {
      result.push({
        id: uid(),
        role: "user",
        content: String(m.content ?? ""),
      });
      i++;
      continue;
    }

    if (role === "assistant") {
      const tcRaw = m.tool_calls as unknown;
      const toolsOpenAi: { id?: string; function?: { name?: string; arguments?: string } }[] =
        Array.isArray(tcRaw) ? (tcRaw as typeof toolsOpenAi) : [];

      const merged: ToolCallUi[] = toolsOpenAi.map((t) => {
        let args: Record<string, unknown> = {};
        const rawArgs = t.function?.arguments;
        if (typeof rawArgs === "string") {
          try {
            args = JSON.parse(rawArgs) as Record<string, unknown>;
          } catch {
            args = {};
          }
        }
        return {
          name: String(t.function?.name ?? ""),
          arguments: args,
        };
      });

      const assistantContent = String(m.content ?? "");
      i++;

      const resultsByToolCallId = new Map<string, Record<string, unknown>>();
      while (i < raw.length && String(raw[i]?.role ?? "") === "tool") {
        const tr = raw[i] as Record<string, unknown>;
        const tid = String(tr.tool_call_id ?? "");
        const parsed =
          tryParseJson(tr.content) ??
          ({ raw: String(tr.content ?? "") } as Record<string, unknown>);
        if (tid) resultsByToolCallId.set(tid, parsed);
        i++;
      }

      for (let k = 0; k < merged.length; k++) {
        const id = toolsOpenAi[k]?.id;
        if (id && resultsByToolCallId.has(id)) {
          merged[k].result = resultsByToolCallId.get(id);
        }
      }

      result.push({
        id: uid(),
        role: "assistant",
        content: assistantContent,
        toolCalls: merged.length ? merged : undefined,
      });
      continue;
    }

    i++;
  }

  return result;
}
