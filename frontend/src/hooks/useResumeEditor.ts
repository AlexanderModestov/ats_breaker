"use client";
import { useState, useCallback, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { editResume, validateResume } from "@/lib/api";
import type { FilterResult, EditResponse } from "@/types";

export function useResumeEditor(runId: string, initialHtml: string) {
  const [html, setHtml] = useState(initialHtml);
  const [history, setHistory] = useState<string[]>([initialHtml]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Requirements (fetched via validate endpoint which returns both)
  const requirementsQuery = useQuery({
    queryKey: ["requirements", runId, html],
    queryFn: () => validateResume(runId, html).then((r) => r.requirements),
    enabled: !!html,
    staleTime: 5000,
  });

  // Validation
  const [validationResults, setValidationResults] = useState<FilterResult[]>([]);

  const runValidation = useCallback(
    async (currentHtml: string) => {
      const res = await validateResume(runId, currentHtml);
      setValidationResults(res.results);
      return res;
    },
    [runId]
  );

  // Push to history
  const pushHtml = useCallback(
    (newHtml: string) => {
      setHtml(newHtml);
      setHistory((prev) => [...prev.slice(0, historyIndex + 1), newHtml]);
      setHistoryIndex((i) => i + 1);

      // Debounced validation
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => runValidation(newHtml), 1000);
    },
    [historyIndex, runValidation]
  );

  // Manual HTML edit (from Monaco)
  const updateHtml = useCallback(
    (newHtml: string) => {
      pushHtml(newHtml);
    },
    [pushHtml]
  );

  // LLM edit
  const editMutation = useMutation({
    mutationFn: (instruction: string) => editResume(runId, instruction, html),
    onSuccess: (data: EditResponse) => {
      pushHtml(data.updated_html);
    },
  });

  // Undo
  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      setHtml(history[newIndex]);
    }
  }, [history, historyIndex]);

  // Redo
  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      setHtml(history[newIndex]);
    }
  }, [history, historyIndex]);

  return {
    html,
    updateHtml,
    requirements: requirementsQuery.data ?? [],
    requirementsLoading: requirementsQuery.isLoading,
    validationResults,
    sendInstruction: editMutation.mutate,
    isEditing: editMutation.isPending,
    editError: editMutation.error,
    undo,
    redo,
    canUndo: historyIndex > 0,
    canRedo: historyIndex < history.length - 1,
  };
}
