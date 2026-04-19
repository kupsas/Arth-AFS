"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessageUi } from "@/lib/chat-types";
import { cn } from "@/lib/utils";

import { ToolCallGroup } from "./tool-call-group";

export function MessageBubble({ message }: { message: ChatMessageUi }) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full flex-col gap-1",
        isUser ? "items-end" : "items-start",
      )}
    >
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="w-full max-w-[95%]">
          <ToolCallGroup tools={message.toolCalls} />
        </div>
      )}
      <div
        className={cn(
          "max-w-[95%] rounded-2xl px-4 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-card text-card-foreground",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <article className="prose prose-sm dark:prose-invert max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 prose-table:text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  );
}
