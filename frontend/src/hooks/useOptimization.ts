"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteOptimization,
  downloadOptimizationPDF,
  getOptimizationStatus,
  listOptimizations,
  startOptimization,
} from "@/lib/api";
import { posthog } from "@/lib/posthog";
import type { OptimizationStatus, OptimizationSummary, OptimizeRequest } from "@/types";

const POLL_INTERVAL = 2000; // 2 seconds

export function useOptimizations() {
  return useQuery<OptimizationSummary[], Error>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
  });
}

export function useStartOptimization() {
  return useMutation({
    mutationFn: (request: OptimizeRequest) => {
      try {
        posthog.capture("optimization_started");
      } catch { /* noop when disabled */ }
      return startOptimization(request);
    },
  });
}

export function useOptimizationStatus(runId: string | null) {
  const [status, setStatus] = useState<OptimizationStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const startedAtRef = useRef<number>(0);
  const terminalFiredRef = useRef<boolean>(false);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    if (!runId) return;
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
        try {
          if (data.status === "complete") {
            posthog.capture("optimization_completed", {
              iterations: data.iterations,
              duration_sec: durationSec,
            });
          } else {
            posthog.capture("optimization_failed", {
              stage: data.current_step,
              error_type: data.error,
            });
          }
        } catch { /* noop */ }
      }
      if (isTerminal) {
        stopPolling();
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Failed to fetch status"));
      stopPolling();
    }
  }, [runId, stopPolling]);

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
    fetchStatus().then(() => setLoading(false));

    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);

    return () => stopPolling();
  }, [runId, fetchStatus, stopPolling]);

  return { status, error, loading, refetch: fetchStatus };
}

export function useDownloadPDF() {
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
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }, []);

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
