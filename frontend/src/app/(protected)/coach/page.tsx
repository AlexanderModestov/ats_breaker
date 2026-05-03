"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Menu } from "lucide-react";
import { motion } from "@/components/motion";
import { CoachChat } from "@/components/CoachChat";
import { StorybankPanel } from "@/components/StorybankPanel";
import { UpgradeOverlay } from "@/components/UpgradeOverlay";
import { CoachSidebar } from "@/components/coach/CoachSidebar";
import { SidebarDrawer } from "@/components/coach/SidebarDrawer";
import { AddPositionDialog } from "@/components/coach/AddPositionDialog";
import {
  useCoachChat,
  useCoachMessages,
  useCoachSessions,
  useCreateThread,
  useDeleteThread,
  useRenameThread,
} from "@/hooks/useCoach";
import { useStorybank } from "@/hooks/useStorybank";
import { useQuery } from "@tanstack/react-query";
import { listOptimizations } from "@/lib/api";
import type { OptimizationSummary } from "@/types";
import { cn } from "@/lib/utils";

const LAST_THREAD_KEY = "coach.lastThreadId";

export default function CoachPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const threadId = searchParams.get("threadId");
  const [activeTab, setActiveTab] = useState<"chat" | "storybank">("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const { data: optimizations = [] } = useQuery<OptimizationSummary[]>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    staleTime: 60_000,
  });
  const { data: sessions = [] } = useCoachSessions();
  const { data: history = [] } = useCoachMessages(threadId);
  const { data: stories = [] } = useStorybank();

  const createThread = useCreateThread();
  const renameThread = useRenameThread();
  const deleteThread = useDeleteThread();

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === threadId) ?? null,
    [sessions, threadId],
  );
  const activeRunId = activeSession?.optimization_run_id ?? null;

  const setActiveThreadId = (id: string | null) => {
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    if (id) params.set("threadId", id);
    else params.delete("threadId");
    router.replace(`/coach${params.toString() ? `?${params.toString()}` : ""}`);
  };

  // Bootstrap from localStorage on first load.
  useEffect(() => {
    if (threadId || sessions.length === 0) return;
    const last = typeof window !== "undefined" ? localStorage.getItem(LAST_THREAD_KEY) : null;
    if (last && sessions.some((s) => s.id === last)) {
      setActiveThreadId(last);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, threadId]);

  // Persist last viewed thread.
  useEffect(() => {
    if (threadId && typeof window !== "undefined") {
      localStorage.setItem(LAST_THREAD_KEY, threadId);
    }
  }, [threadId]);

  const { streamingMessages, isStreaming, sendMessage } = useCoachChat({
    threadId,
    optimizationRunId: activeRunId,
    onThreadCreated: (newId) => setActiveThreadId(newId),
  });

  const messages = streamingMessages ?? history;

  const existingPositionIds = useMemo(
    () => new Set(sessions.map((s) => s.optimization_run_id)),
    [sessions],
  );

  const handleNewThreadInPosition = (runId: string) => {
    // If there's already an empty thread in this position, reuse it.
    const empty = sessions.find(
      (s) => s.optimization_run_id === runId && s.message_count === 0,
    );
    if (empty) {
      setActiveThreadId(empty.id);
      return;
    }
    createThread.mutate(runId, {
      onSuccess: (created) => setActiveThreadId(created.id),
    });
  };

  const handleDelete = (id: string) => {
    deleteThread.mutate(id, {
      onSuccess: () => {
        if (id === threadId) {
          // Pick fallback: another thread in same position, else any, else null.
          const sameGroup = sessions.find(
            (s) => s.id !== id && s.optimization_run_id === activeRunId,
          );
          const anyOther = sessions.find((s) => s.id !== id);
          setActiveThreadId((sameGroup ?? anyOther)?.id ?? null);
        }
      },
    });
  };

  const handleSend = (content: string) => {
    if (!threadId && !activeRunId) return;
    sendMessage(content, history);
  };

  const sidebar = (
    <CoachSidebar
      sessions={sessions}
      positions={optimizations}
      activeThreadId={threadId}
      onSelectThread={(id) => {
        setActiveThreadId(id);
        setDrawerOpen(false);
      }}
      onCreateThreadInPosition={handleNewThreadInPosition}
      onAddPosition={() => setPickerOpen(true)}
      onRenameThread={(id, title) => renameThread.mutate({ threadId: id, title })}
      onDeleteThread={handleDelete}
    />
  );

  const headerLabel = activeSession
    ? activeSession.title ?? activeSession.preview ?? "New thread"
    : "Coach";

  return (
    <UpgradeOverlay feature="coach">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mx-auto flex h-[calc(100vh-8rem)] max-w-7xl"
      >
        {/* Web: persistent sidebar */}
        <div className="hidden md:block w-[280px] shrink-0">{sidebar}</div>

        {/* Mobile: drawer */}
        <SidebarDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          {sidebar}
        </SidebarDrawer>

        <div className="flex flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <button
              type="button"
              className="md:hidden p-1"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open thread list"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="flex-1 truncate text-sm font-medium">{headerLabel}</span>
            <div className="flex rounded-lg border border-border bg-muted p-0.5 text-sm shrink-0">
              <button
                className={cn(
                  "rounded-md px-3 py-1 font-medium",
                  activeTab === "chat"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
                onClick={() => setActiveTab("chat")}
              >
                Chat
              </button>
              <button
                className={cn(
                  "rounded-md px-3 py-1 font-medium",
                  activeTab === "storybank"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
                onClick={() => setActiveTab("storybank")}
              >
                Storybank ({stories.length})
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            {activeTab === "chat" ? (
              threadId || activeRunId ? (
                <CoachChat
                  messages={messages}
                  isStreaming={isStreaming}
                  onSend={handleSend}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  <p className="text-sm">Pick a thread or add a position to start.</p>
                </div>
              )
            ) : (
              <StorybankPanel />
            )}
          </div>
        </div>

        <AddPositionDialog
          open={pickerOpen}
          positions={optimizations}
          existingPositionIds={existingPositionIds}
          onPick={handleNewThreadInPosition}
          onClose={() => setPickerOpen(false)}
        />
      </motion.div>
    </UpgradeOverlay>
  );
}
