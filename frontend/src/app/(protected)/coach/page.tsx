"use client";

import { useState, useEffect } from "react";
import { motion } from "@/components/motion";
import { CoachChat } from "@/components/CoachChat";
import { StorybankPanel } from "@/components/StorybankPanel";
import { useCoachChat, useCoachMessages } from "@/hooks/useCoach";
import { useStorybank } from "@/hooks/useStorybank";
import { useQuery } from "@tanstack/react-query";
import { listOptimizations } from "@/lib/api";
import type { OptimizationSummary } from "@/types";

export default function CoachPage() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [storybankCollapsed, setStorybankCollapsed] = useState(false);

  const { data: optimizations = [] } = useQuery<OptimizationSummary[]>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    staleTime: 60_000,
  });

  // Only completed optimizations with parsed job data
  const positions = optimizations.filter(
    (o) => o.status === "complete" && o.job_title
  );

  const {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    loadHistory,
    resetChat,
  } = useCoachChat();

  // Load existing messages when session changes
  const { data: history } = useCoachMessages(sessionId);
  useEffect(() => {
    if (history && history.length > 0) {
      loadHistory(history);
    }
  }, [history, loadHistory]);

  // Reset chat when position changes
  const handlePositionChange = (runId: string) => {
    setSelectedRunId(runId);
    resetChat();
  };

  const handleSend = (content: string) => {
    if (!selectedRunId) return;
    sendMessage(selectedRunId, content);
  };

  // Refetch storybank after streaming completes (coach may have saved stories)
  const { refetch: refetchStorybank } = useStorybank();
  useEffect(() => {
    if (!isStreaming && sessionId) {
      refetchStorybank();
    }
  }, [isStreaming, sessionId, refetchStorybank]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex h-[calc(100vh-4rem)] max-w-7xl"
    >
      {/* Chat area */}
      <div className="flex flex-1 flex-col">
        {/* Position selector */}
        <div className="border-b border-border px-4 py-3">
          <select
            value={selectedRunId || ""}
            onChange={(e) => handlePositionChange(e.target.value)}
            className="w-full max-w-md rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="" disabled>
              Select a position...
            </option>
            {positions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.job_company} — {p.job_title}
              </option>
            ))}
          </select>
        </div>

        {/* Chat */}
        {selectedRunId ? (
          <CoachChat
            messages={messages}
            isStreaming={isStreaming}
            onSend={handleSend}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <p className="text-sm">Select a position to start coaching</p>
          </div>
        )}
      </div>

      {/* Storybank panel — desktop only */}
      <div
        className={
          storybankCollapsed ? "hidden" : "hidden w-80 shrink-0 lg:block"
        }
      >
        <StorybankPanel
          collapsed={storybankCollapsed}
          onToggle={() => setStorybankCollapsed(!storybankCollapsed)}
        />
      </div>
      {storybankCollapsed && (
        <StorybankPanel
          collapsed={true}
          onToggle={() => setStorybankCollapsed(false)}
        />
      )}
    </motion.div>
  );
}
