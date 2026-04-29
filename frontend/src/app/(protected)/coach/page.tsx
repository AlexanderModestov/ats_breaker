"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "@/components/motion";
import { CoachChat } from "@/components/CoachChat";
import { StorybankPanel } from "@/components/StorybankPanel";
import { UpgradeOverlay } from "@/components/UpgradeOverlay";
import { useCoachChat, useCoachMessages } from "@/hooks/useCoach";
import { useStorybank } from "@/hooks/useStorybank";
import { useQuery } from "@tanstack/react-query";
import { listOptimizations } from "@/lib/api";
import type { OptimizationSummary } from "@/types";
import { cn } from "@/lib/utils";

export default function CoachPage() {
  const searchParams = useSearchParams();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"chat" | "storybank">("chat");

  useEffect(() => {
    const runId = searchParams.get("runId");
    if (runId) setSelectedRunId(runId);
  }, [searchParams]);

  const { data: optimizations = [] } = useQuery<OptimizationSummary[]>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    staleTime: 60_000,
  });

  // Only completed optimizations with parsed job data
  const positions = optimizations.filter(
    (o) => o.status === "complete" && o.job_title
  );

  const { data: stories = [] } = useStorybank();
  const storybankCount = stories.length;

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

  return (
    <UpgradeOverlay feature="coach">
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mx-auto flex h-[calc(100vh-4rem)] max-w-7xl flex-col"
    >
      {/* Header: position selector + tabs */}
      <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <select
          value={selectedRunId || ""}
          onChange={(e) => handlePositionChange(e.target.value)}
          className="flex-1 max-w-md rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
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

        {/* Tab switcher */}
        <div className="flex rounded-lg border border-border bg-muted p-0.5 text-sm shrink-0">
          <button
            type="button"
            className={cn(
              "rounded-md px-4 py-1.5 font-medium transition-colors",
              activeTab === "chat"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            className={cn(
              "flex items-center gap-1.5 rounded-md px-4 py-1.5 font-medium transition-colors",
              activeTab === "storybank"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            onClick={() => setActiveTab("storybank")}
          >
            Storybank
            {storybankCount > 0 && (
              <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">
                {storybankCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "chat" ? (
          selectedRunId ? (
            <CoachChat
              messages={messages}
              isStreaming={isStreaming}
              onSend={handleSend}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <p className="text-sm">Select a position to start coaching</p>
            </div>
          )
        ) : (
          <StorybankPanel />
        )}
      </div>
    </motion.div>
    </UpgradeOverlay>
  );
}
