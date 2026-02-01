"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  downloadOptimizationPDF,
  getOptimizationStatus,
  startOptimization,
} from "@/lib/api";
import type { OptimizationStatus, OptimizeRequest } from "@/types";

const POLL_INTERVAL = 2000; // 2 seconds

export function useStartOptimization() {
  return useMutation({
    mutationFn: (request: OptimizeRequest) => startOptimization(request),
  });
}

export function useOptimizationStatus(runId: string | null) {
  const [status, setStatus] = useState<OptimizationStatus | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

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

      // Stop polling if complete or failed
      if (data.status === "complete" || data.status === "failed") {
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
      return;
    }

    setLoading(true);
    fetchStatus().then(() => setLoading(false));

    // Start polling
    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);

    return () => {
      stopPolling();
    };
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
