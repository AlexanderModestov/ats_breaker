"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteOptimization,
  downloadOptimizationPDF,
  getOptimizationStatus,
  listOptimizations,
  startOptimization,
  updateOptimizationJob,
} from "@/lib/api";
import { useAnalytics } from "@/hooks/useAnalytics";
import type { OptimizationStatus, OptimizationSummary, OptimizeRequest } from "@/types";

// Optimization runs ~3-5 minutes. Poll fast at the start so early status
// transitions feel responsive, then back off to reduce backend load.
const POLL_INTERVAL_FAST = 2000; // first 20s
const POLL_INTERVAL_SLOW = 5000; // after that
const POLL_FAST_DURATION_MS = 20_000;
const ERROR_MESSAGE_MAX_LEN = 120;

export function useOptimizations() {
  return useQuery<OptimizationSummary[], Error>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
  });
}

export function useStartOptimization() {
  const { track } = useAnalytics();
  return useMutation({
    mutationFn: (request: OptimizeRequest) => {
      track("optimization_started");
      return startOptimization(request);
    },
  });
}

export function useOptimizationStatus(runId: string | null) {
  const { track } = useAnalytics();
  const [status, setStatus] = useState<OptimizationStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const startedAtRef = useRef<number>(0);
  const terminalFiredRef = useRef<boolean>(false);

  const stopPolling = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async (): Promise<boolean> => {
    if (!runId) return true;
    try {
      const data = await getOptimizationStatus(runId);
      setStatus(data);
      setError(null);

      const isTerminal = data.status === "complete" || data.status === "failed";
      if (isTerminal && !terminalFiredRef.current) {
        terminalFiredRef.current = true;
        const durationSec = startedAtRef.current
          ? Math.round((Date.now() - startedAtRef.current) / 1000)
          : undefined;
        if (data.status === "complete") {
          track("optimization_completed", {
            iterations: data.iterations,
            duration_sec: durationSec,
          });
        } else {
          track("optimization_failed", {
            stage: data.current_step,
            error_message: data.error?.slice(0, ERROR_MESSAGE_MAX_LEN) ?? null,
          });
        }
      }
      return isTerminal;
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Failed to fetch status"));
      return true;
    }
  }, [runId, track]);

  useEffect(() => {
    if (!runId) {
      setStatus(null);
      setError(null);
      setLoading(false);
      terminalFiredRef.current = false;
      startedAtRef.current = 0;
      return;
    }

    setLoading(true);
    terminalFiredRef.current = false;
    startedAtRef.current = Date.now();
    let cancelled = false;

    const schedule = (delay: number) => {
      timeoutRef.current = setTimeout(async () => {
        if (cancelled) return;
        const done = await fetchStatus();
        if (cancelled || done) return;
        const elapsed = Date.now() - startedAtRef.current;
        const next = elapsed < POLL_FAST_DURATION_MS
          ? POLL_INTERVAL_FAST
          : POLL_INTERVAL_SLOW;
        schedule(next);
      }, delay);
    };

    fetchStatus().then((done) => {
      setLoading(false);
      if (!cancelled && !done) schedule(POLL_INTERVAL_FAST);
    });

    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [runId, fetchStatus, stopPolling]);

  return { status, error, loading, refetch: fetchStatus };
}

export function useDownloadPDF() {
  const { track } = useAnalytics();
  const [downloading, setDownloading] = useState(false);

  const download = useCallback(async (runId: string, filename?: string) => {
    setDownloading(true);
    try {
      const blob = await downloadOptimizationPDF(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || `resume_${runId}.pdf`;
      document.body.appendChild(a);
      a.click();
      track("pdf_downloaded");
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }, [track]);

  return { download, downloading };
}

export function useDeleteOptimization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (runId: string) => deleteOptimization(runId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["optimizations"] });
    },
  });
}

export function useUpdateOptimizationJob(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: { title?: string; company?: string }) =>
      updateOptimizationJob(runId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["optimization", runId] });
      queryClient.invalidateQueries({ queryKey: ["optimizations"] });
    },
  });
}
