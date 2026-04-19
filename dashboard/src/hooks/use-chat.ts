"use client";

/**
 * WebSocket hook for the Arth agent chat — wires server events into UI messages.
 *
 * Connection URL follows ``NEXT_PUBLIC_API_URL`` / same-origin rules (see ``api-base.ts``).
 * When the URL has no ``session_id``, FastAPI creates a thread and emits ``session_ready``.
 *
 * In same-origin mode, the WS bypasses the Next.js proxy (which can't upgrade
 * WebSocket) and connects directly to FastAPI.  A one-time auth ticket fetched
 * via REST (where the httpOnly cookie *does* travel through the proxy) is passed
 * as ``?ticket=`` so FastAPI can authenticate the connection.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { apiViaSameOrigin, buildChatWebSocketUrl } from "@/lib/api-base";
import type {
  ChatMessageUi,
  ClientChatWireMessage,
  LiveTool,
  ToolCallUi,
} from "@/lib/chat-types";
import { normalizeOpenAiMessagesToUi } from "@/lib/chat-types";
import { fetchChatSession, fetchWsTicket } from "@/lib/api";

export type ChatConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "error";

function uuid(): string {
  return crypto.randomUUID?.() ?? `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function useChat(
  sessionIdProp: string | undefined,
  onSessionReady?: (sessionId: string) => void,
) {
  const onReadyRef = useRef(onSessionReady);
  onReadyRef.current = onSessionReady;
  const [messages, setMessages] = useState<ChatMessageUi[]>([]);
  const [connection, setConnection] = useState<ChatConnectionStatus>("connecting");
  const [isGenerating, setIsGenerating] = useState(false);
  /** Tool names shown live under “Arth is thinking…” while the turn runs (mirrors WS events). */
  const [liveTools, setLiveTools] = useState<LiveTool[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  /** Assistant row being filled for the current turn (tools + final text). */
  const liveAssistantRef = useRef<{ id: string; tools: ToolCallUi[] } | null>(
    null,
  );

  /** Hydrate transcript when switching threads (REST — same rows the agent loads server-side). */
  useEffect(() => {
    if (!sessionIdProp) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    fetchChatSession(sessionIdProp)
      .then((d) => {
        if (!cancelled)
          setMessages(normalizeOpenAiMessagesToUi(d.messages ?? []));
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionIdProp]);

  /** One WebSocket per ``sessionIdProp`` (selected thread or "new").
   *  In same-origin mode, fetch a one-time ticket via REST first (the cookie
   *  travels through the proxy), then pass it as ``?ticket=`` to FastAPI. */
  useEffect(() => {
    let cancelled = false;
    setConnection("connecting");
    setLastError(null);

    function openSocket(ticket?: string) {
      if (cancelled) return;
      const url = buildChatWebSocketUrl(sessionIdProp, ticket);
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnection("open");
      };

      ws.onclose = () => {
        setConnection("closed");
        if (wsRef.current === ws) wsRef.current = null;
      };

      ws.onerror = () => {
        setConnection("error");
        setLastError(
          "Could not connect to the chat server. Is the API running, and does your WebSocket URL match the API (see NEXT_PUBLIC_API_URL)?",
        );
      };

      ws.onmessage = (evt) => {
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(String(evt.data)) as Record<string, unknown>;
        } catch {
          return;
        }
        const typ = String(data.type ?? "");

        if (typ === "session_ready") {
          const sid = String(data.session_id ?? "");
          if (sid) onReadyRef.current?.(sid);
          return;
        }

        if (typ === "screening_blocked") {
          const msg = String(data.message ?? "");
          setMessages((prev) => [
            ...prev,
            { id: uuid(), role: "assistant", content: msg },
          ]);
          setIsGenerating(false);
          liveAssistantRef.current = null;
          setLiveTools([]);
          return;
        }

        if (typ === "tool_call_started") {
          setIsGenerating(true);
          if (!liveAssistantRef.current) {
            liveAssistantRef.current = { id: uuid(), tools: [] };
          }
          liveAssistantRef.current.tools.push({
            name: String(data.tool_name ?? ""),
            arguments:
              typeof data.arguments === "object" &&
              data.arguments !== null &&
              !Array.isArray(data.arguments)
                ? (data.arguments as Record<string, unknown>)
                : {},
          });
          setLiveTools((prev) => [
            ...prev,
            { name: String(data.tool_name ?? ""), status: "running" },
          ]);
          return;
        }

        if (typ === "tool_call_completed") {
          const tools = liveAssistantRef.current?.tools;
          if (tools?.length) {
            const name = String(data.tool_name ?? "");
            const result =
              typeof data.result === "object" &&
              data.result !== null &&
              !Array.isArray(data.result)
                ? (data.result as Record<string, unknown>)
                : {};
            const duration_ms = Number(data.duration_ms ?? 0);
            for (let i = tools.length - 1; i >= 0; i--) {
              if (tools[i].name === name && tools[i].result === undefined) {
                tools[i].result = result;
                tools[i].duration_ms = duration_ms;
                break;
              }
            }
          }
          setLiveTools((prev) => {
            const next = [...prev];
            const name = String(data.tool_name ?? "");
            for (let i = next.length - 1; i >= 0; i--) {
              if (next[i].name === name && next[i].status === "running") {
                next[i] = { ...next[i], status: "done" };
                break;
              }
            }
            return next;
          });
          return;
        }

        if (typ === "response") {
          const text = String(data.content ?? "");
          setMessages((prev) => {
            const live = liveAssistantRef.current;
            liveAssistantRef.current = null;
            if (live) {
              return [
                ...prev,
                {
                  id: live.id,
                  role: "assistant",
                  content: text,
                  toolCalls: live.tools.length ? live.tools : undefined,
                },
              ];
            }
            return [...prev, { id: uuid(), role: "assistant", content: text }];
          });
          return;
        }

        if (typ === "error") {
          const msg = String(data.message ?? "Error");
          setMessages((prev) => [
            ...prev,
            { id: uuid(), role: "assistant", content: msg },
          ]);
          setLiveTools([]);
          return;
        }

        if (typ === "done") {
          setIsGenerating(false);
          liveAssistantRef.current = null;
          setLiveTools([]);
          return;
        }

        // llm_step / token — UI ignores (final ``response`` carries text).
      };
    }

    if (apiViaSameOrigin) {
      fetchWsTicket()
        .then((res) => openSocket(res.ticket))
        .catch(() => {
          if (!cancelled) {
            setConnection("error");
            setLastError("Failed to obtain WebSocket auth ticket. Are you logged in?");
          }
        });
    } else {
      openSocket();
    }

    return () => {
      cancelled = true;
      const ws = wsRef.current;
      if (ws) {
        ws.close();
        if (wsRef.current === ws) wsRef.current = null;
      }
    };
  }, [sessionIdProp]);

  const sendMessage = useCallback((raw: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const content = raw.trim();
    if (!content) return;

    setMessages((prev) => [
      ...prev,
      { id: uuid(), role: "user", content },
    ]);
    setIsGenerating(true);
    setLiveTools([]);

    const payload: ClientChatWireMessage = { type: "send_message", content };
    ws.send(JSON.stringify(payload));
  }, []);

  const stopGenerating = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const payload: ClientChatWireMessage = { type: "stop" };
    ws.send(JSON.stringify(payload));
  }, []);

  return {
    messages,
    connection,
    isGenerating,
    liveTools,
    lastError,
    sendMessage,
    stopGenerating,
  };
}
