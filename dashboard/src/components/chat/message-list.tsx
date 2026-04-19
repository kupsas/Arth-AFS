"use client";

import { useEffect, useRef } from "react";

import type { ChatMessageUi, LiveTool } from "@/lib/chat-types";

import { MessageBubble } from "./message-bubble";
import { StreamingIndicator } from "./streaming-indicator";

export function MessageList({
  messages,
  isGenerating,
  liveTools,
}: {
  messages: ChatMessageUi[];
  isGenerating: boolean;
  /** Live tool names while the assistant turn is in flight (from WebSocket). */
  liveTools?: LiveTool[];
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isGenerating, liveTools?.length]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      {isGenerating && <StreamingIndicator liveTools={liveTools} />}
      <div ref={bottomRef} className="h-1 shrink-0" aria-hidden />
    </div>
  );
}
