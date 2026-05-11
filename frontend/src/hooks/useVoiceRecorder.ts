"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { pickRecorderMimeType } from "@/lib/utils";

export type RecorderState = "idle" | "recording" | "uploading" | "error";

export type RecorderError =
  | "permission_denied"
  | "no_microphone"
  | "unsupported"
  | "too_short"
  | "max_duration"
  | "unknown";

const MIN_DURATION_MS = 500;
const MAX_DURATION_MS = 60_000;

interface UseVoiceRecorderResult {
  state: RecorderState;
  durationMs: number;
  error: RecorderError | null;
  /** Begin capture. Resolves once recording has actually started (or rejects). */
  start: () => Promise<void>;
  /** Stop and resolve with the blob (or null if too short or empty). */
  stop: () => Promise<Blob | null>;
  /** Stop and discard. */
  cancel: () => void;
  /** Mark the hook as uploading / done — purely cosmetic for the UI button. */
  setUploading: (uploading: boolean) => void;
  /** Reset back to idle. */
  reset: () => void;
}

export function useVoiceRecorder(): UseVoiceRecorderResult {
  const [state, setState] = useState<RecorderState>("idle");
  const [durationMs, setDurationMs] = useState(0);
  const [error, setError] = useState<RecorderError | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef<number>(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  const cleanup = useCallback(() => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (maxTimerRef.current) clearTimeout(maxTimerRef.current);
    tickRef.current = null;
    maxTimerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    chunksRef.current = [];
  }, []);

  useEffect(() => () => cleanup(), [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    cancelledRef.current = false;
    const mime = pickRecorderMimeType();
    if (!mime) {
      setError("unsupported");
      setState("error");
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name;
      setError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "permission_denied"
          : name === "NotFoundError" || name === "NotReadableError"
            ? "no_microphone"
            : "unknown",
      );
      setState("error");
      throw e;
    }

    const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 32000 });
    recorderRef.current = recorder;
    streamRef.current = stream;
    chunksRef.current = [];

    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
    };

    startedAtRef.current = performance.now();
    setDurationMs(0);
    tickRef.current = setInterval(() => {
      setDurationMs(Math.round(performance.now() - startedAtRef.current));
    }, 100);

    maxTimerRef.current = setTimeout(() => {
      if (recorderRef.current?.state === "recording") {
        setError("max_duration");
        recorderRef.current.stop();
      }
    }, MAX_DURATION_MS);

    recorder.start();
    setState("recording");
  }, []);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state !== "recording") {
      cleanup();
      setState("idle");
      return null;
    }
    const elapsed = performance.now() - startedAtRef.current;
    return new Promise<Blob | null>((resolve) => {
      recorder.onstop = () => {
        const chunks = chunksRef.current;
        const mime = recorder.mimeType || "audio/webm";
        const blob = chunks.length ? new Blob(chunks, { type: mime }) : null;
        const tooShort = elapsed < MIN_DURATION_MS;
        cleanup();
        if (cancelledRef.current) {
          setState("idle");
          resolve(null);
          return;
        }
        if (tooShort) {
          setError("too_short");
          setState("error");
          resolve(null);
          return;
        }
        setState("idle");
        resolve(blob);
      };
      recorder.stop();
    });
  }, [cleanup]);

  const cancel = useCallback(() => {
    cancelledRef.current = true;
    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") recorder.stop();
    else {
      cleanup();
      setState("idle");
    }
  }, [cleanup]);

  const setUploading = useCallback((uploading: boolean) => {
    setState(uploading ? "uploading" : "idle");
  }, []);

  const reset = useCallback(() => {
    setError(null);
    setState("idle");
    setDurationMs(0);
  }, []);

  return { state, durationMs, error, start, stop, cancel, setUploading, reset };
}
