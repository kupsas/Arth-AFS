"use client";

import type {
  ActivitySegment,
  ChatMessageUi,
  ChatSessionSummary,
  LiveTool,
  ToolCallUi,
} from "@/lib/chat-types";
import type { ProviderFailurePayload } from "@/lib/api";

import { ChatPanel } from "./chat-panel";
import { SessionSidebar } from "./session-sidebar";

export function ChatLayout({
  sessions,
  sessionsLoading,
  activeSessionId,
  messages,
  connectionOk,
  isGenerating,
  isResponseStreaming,
  liveTools,
  liveThinking,
  isThinking,
  liveActivitySegments,
  liveWipTools,
  lastError,
  agentPausedFailures,
  onDismissAgentPaused,
  onRetryAgentPaused,
  onSwitchProviderKeys,
  onNewChat,
  onSelectSession,
  onArchiveSession,
  onSend,
  onStop,
}: {
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;
  activeSessionId: string | undefined;
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
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onArchiveSession: (id: string) => void;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-[28rem] gap-0 rounded-xl border border-border bg-card shadow-sm">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        loading={sessionsLoading}
        onNewChat={onNewChat}
        onSelectSession={onSelectSession}
        onArchiveSession={onArchiveSession}
      />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col p-4">
        <ChatPanel
          messages={messages}
          connectionOk={connectionOk}
          isGenerating={isGenerating}
          isResponseStreaming={isResponseStreaming}
          liveTools={liveTools}
          liveThinking={liveThinking}
          isThinking={isThinking}
          liveActivitySegments={liveActivitySegments}
          liveWipTools={liveWipTools}
          lastError={lastError}
          agentPausedFailures={agentPausedFailures}
          onDismissAgentPaused={onDismissAgentPaused}
          onRetryAgentPaused={onRetryAgentPaused}
          onSwitchProviderKeys={onSwitchProviderKeys}
          onSend={onSend}
          onStop={onStop}
        />
      </div>
    </div>
  );
}
