"use client";

import { useState, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  listCoachSessions,
  getCoachMessages,
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

export function useCoachMessages(sessionId: string | null) {
  return useQuery<CoachMessage[]>({
    queryKey: ["coach-messages", sessionId],
    queryFn: () => getCoachMessages(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  });
}

export function useCoachChat() {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef(false);

  const loadHistory = useCallback((history: CoachMessage[]) => {
    setMessages(history);
  }, []);

  const sendMessage = useCallback(
    async (optimizationRunId: string, content: string) => {
      if (isStreaming) return;

      const userMsg: CoachMessage = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);
      abortRef.current = false;

      const assistantMsg: CoachMessage = { role: "assistant", content: "" };
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        await streamCoachChat(
          optimizationRunId,
          content,
          sessionId ?? undefined,
          (delta) => {
            if (abortRef.current) return;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + delta,
                };
              }
              return updated;
            });
          },
          (newSessionId) => {
            setSessionId(newSessionId);
            setIsStreaming(false);
          },
          (error) => {
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                role: "assistant",
                content: `Error: ${error}`,
              };
              return updated;
            });
            setIsStreaming(false);
          }
        );
      } catch (e) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `Error: ${e instanceof Error ? e.message : "Unknown error"}`,
          };
          return updated;
        });
        setIsStreaming(false);
      }
    },
    [isStreaming, sessionId]
  );

  const resetChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    abortRef.current = true;
    setIsStreaming(false);
  }, []);

  return {
    messages,
    isStreaming,
    sessionId,
    sendMessage,
    loadHistory,
    resetChat,
    setSessionId,
  };
}
