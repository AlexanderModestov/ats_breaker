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
import { useAnalytics } from "@/hooks/useAnalytics";
import type { OptimizationStatus, OptimizationSummary, OptimizeRequest } from "@/types";

const POLL_INTERVAL = 2000; // 2 seconds
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
      if (isTerminal) {
        stopPolling();
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Failed to fetch status"));
      stopPolling();
    }
  }, [runId, stopPolling, track]);

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
