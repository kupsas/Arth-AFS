"use client";

import type {
  ActivitySegment,
  ChatMessageUi,
  LiveTool,
  ToolCallUi,
} from "@/lib/chat-types";

import { ProviderPausedDialog } from "@/components/shared/provider-paused-dialog";
import type { ProviderFailurePayload } from "@/lib/api";

import { ChatInput } from "./chat-input";
import { MessageList } from "./message-list";

const STARTERS = [
  "Kuch poocho — kitna kharcha food pe is month?",
  "How much did I spend on food this month?",
  "What's my net worth right now?",
  "What's my savings rate for the last 3 months?",
  "Show me my asset allocation.",
];

export function ChatPanel({
  messages,
  connectionOk,
  isGenerating,
  isResponseStreaming,
  liveTools,
  liveThinking = "",
  isThinking = false,
  liveActivitySegments = [],
  liveWipTools = [],
  lastError,
  agentPausedFailures,
  onDismissAgentPaused,
  onRetryAgentPaused,
  onSwitchProviderKeys,
  onSend,
  onStop,
}: {
  messages: ChatMessageUi[];
  connectionOk: boolean;
  isGenerating: boolean;
  isResponseStreaming?: boolean;
  liveTools?: LiveTool[];
  liveThinking?: string;
  isThinking?: boolean;
  liveActivitySegments?: ActivitySegment[];
  liveWipTools?: ToolCallUi[];
  lastError: string | null;
  agentPausedFailures: ProviderFailurePayload[] | null;
  onDismissAgentPaused: () => void;
  onRetryAgentPaused: () => void;
  onSwitchProviderKeys: () => void;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const ready = connectionOk;

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <ProviderPausedDialog
        open={agentPausedFailures !== null && agentPausedFailures.length > 0}
        onOpenChange={(o) => {
          if (!o) onDismissAgentPaused();
        }}
        failures={agentPausedFailures ?? []}
        context="chat"
        onSwitchProvider={onSwitchProviderKeys}
        onTryAgain={onRetryAgentPaused}
      />

      {lastError && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {lastError}
        </p>
      )}

      {messages.length === 0 && ready && (
        <div className="rounded-xl border border-dashed border-border bg-muted/10 p-6">
          <p className="mb-3 text-sm font-medium text-foreground">
            Ask Arth anything about your money
          </p>
          <p className="mb-3 text-xs text-muted-foreground">
            Try one of these to get started:
          </p>
          <ul className="flex flex-col gap-2">
            {STARTERS.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  disabled={isGenerating}
                  onClick={() => onSend(q)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-left text-sm transition hover:bg-muted disabled:opacity-50"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <MessageList
        messages={messages}
        isGenerating={isGenerating}
        isResponseStreaming={isResponseStreaming}
        liveTools={liveTools}
        liveThinking={liveThinking}
        isThinking={isThinking}
        liveActivitySegments={liveActivitySegments}
        liveWipTools={liveWipTools}
      />

      <ChatInput
        disabled={!ready}
        isGenerating={isGenerating}
        onSend={onSend}
        onStop={onStop}
      />
    </section>
  );
}
