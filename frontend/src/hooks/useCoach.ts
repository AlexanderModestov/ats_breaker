"use client";

import { useState, useCallback, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCoachThread,
  deleteCoachThread,
  getCoachMessages,
  listCoachSessions,
  renameCoachThread,
  streamCoachChat,
} from "@/lib/api";
import type { CoachMessage, CoachSession } from "@/types";

export function useCoachSessions() {
  return useQuery<CoachSession[]>({
    queryKey: ["coach-sessions"],
    queryFn: listCoachSessions,
    staleTime: 60_000,
  });
}

export function useCoachMessages(threadId: string | null) {
  return useQuery<CoachMessage[]>({
    queryKey: ["coach-messages", threadId],
    queryFn: () => getCoachMessages(threadId!),
    enabled: !!threadId,
    staleTime: 30_000,
  });
}

export function useCreateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (optimizationRunId: string) => createCoachThread(optimizationRunId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coach-sessions"] }),
  });
}

export function useRenameThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string | null }) =>
      renameCoachThread(threadId, title),
    onMutate: async ({ threadId, title }) => {
      await qc.cancelQueries({ queryKey: ["coach-sessions"] });
      const prev = qc.getQueryData<CoachSession[]>(["coach-sessions"]);
      qc.setQueryData<CoachSession[]>(["coach-sessions"], (old) =>
        old?.map((s) => (s.id === threadId ? { ...s, title } : s)) ?? [],
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["coach-sessions"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["coach-sessions"] }),
  });
}

export function useDeleteThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => deleteCoachThread(threadId),
    onSuccess: (_, threadId) => {
      qc.invalidateQueries({ queryKey: ["coach-sessions"] });
      qc.removeQueries({ queryKey: ["coach-messages", threadId] });
    },
  });
}

interface UseCoachChatArgs {
  threadId: string | null;
  optimizationRunId: string | null;
  onThreadCreated: (newThreadId: string) => void;
}

export function useCoachChat({
  threadId,
  optimizationRunId,
  onThreadCreated,
}: UseCoachChatArgs) {
  const qc = useQueryClient();
  const [streamingMessages, setStreamingMessages] = useState<CoachMessage[] | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const inFlightThreadIdRef = useRef<string | null>(null);

  const sendMessage = useCallback(
    async (content: string, baseHistory: CoachMessage[]) => {
      if (isStreaming) return;
      if (!threadId && !optimizationRunId) return;

      inFlightThreadIdRef.current = threadId; // null if first message in lazy thread
      setIsStreaming(true);

      const userMsg: CoachMessage = { role: "user", content };
      const assistantMsg: CoachMessage = { role: "assistant", content: "" };
      setStreamingMessages([...baseHistory, userMsg, assistantMsg]);

      const args = threadId
        ? ({ threadId } as const)
        : ({ optimizationRunId: optimizationRunId! } as const);

      try {
        await streamCoachChat(
          args,
          content,
          (delta) => {
            // Only update UI if user hasn't switched threads.
            const currentInFlight = inFlightThreadIdRef.current;
            if (threadId && currentInFlight !== threadId) return;
            setStreamingMessages((prev) => {
              if (!prev) return prev;
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, content: last.content + delta };
              }
              return updated;
            });
          },
          (newThreadId) => {
            setIsStreaming(false);
            qc.invalidateQueries({ queryKey: ["coach-sessions"] });
            qc.invalidateQueries({ queryKey: ["coach-messages", newThreadId] });
            setStreamingMessages(null);
            if (!threadId) onThreadCreated(newThreadId);
          },
          (err) => {
            setIsStreaming(false);
            const currentInFlight = inFlightThreadIdRef.current;
            if (threadId && currentInFlight !== threadId) return;
            setStreamingMessages((prev) => {
              if (!prev) return prev;
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: `Error: ${err}` };
              return updated;
            });
          },
        );
      } catch (e) {
        setIsStreaming(false);
        const currentInFlight = inFlightThreadIdRef.current;
        if (threadId && currentInFlight !== threadId) return;
        const msg = e instanceof Error ? e.message : "Unknown error";
        setStreamingMessages((prev) => {
          if (!prev) return prev;
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `Error: ${msg}` };
          return updated;
        });
      }
    },
    [isStreaming, threadId, optimizationRunId, onThreadCreated, qc],
  );

  return { streamingMessages, isStreaming, sendMessage };
}
