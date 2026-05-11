"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useVoiceRecorder, type RecorderError } from "@/hooks/useVoiceRecorder";

const SWIPE_CANCEL_PX = -80;

interface VoiceButtonProps {
  disabled?: boolean;
  /** Called with the captured audio blob. Caller transcribes + sends. */
  onCaptured: (blob: Blob) => Promise<void>;
  /** Called on user-visible errors so the parent can surface a message. */
  onError: (kind: RecorderError) => void;
  /** Optional telemetry hooks. */
  onRecordingStart?: () => void;
  onRecordingEnd?: (info: { durationMs: number; cancelled: boolean }) => void;
}

function formatDuration(ms: number): string {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function VoiceButton({
  disabled,
  onCaptured,
  onError,
  onRecordingStart,
  onRecordingEnd,
}: VoiceButtonProps) {
  const recorder = useVoiceRecorder();
  const [willCancel, setWillCancel] = useState(false);
  const startXRef = useRef<number | null>(null);

  // Surface hook errors upward.
  useEffect(() => {
    if (recorder.error) {
      onError(recorder.error);
      onRecordingEnd?.({ durationMs: recorder.durationMs, cancelled: true });
      recorder.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder.error]);

  const handleStart = async (clientX: number) => {
    if (disabled || recorder.state !== "idle") return;
    startXRef.current = clientX;
    setWillCancel(false);
    try {
      await recorder.start();
      onRecordingStart?.();
    } catch {
      // Error already set inside the hook; effect above will surface it.
    }
  };

  const handleMove = (clientX: number) => {
    if (recorder.state !== "recording" || startXRef.current === null) return;
    setWillCancel(clientX - startXRef.current < SWIPE_CANCEL_PX);
  };

  const handleEnd = async () => {
    if (recorder.state !== "recording") return;
    if (willCancel) {
      const dur = recorder.durationMs;
      recorder.cancel();
      onRecordingEnd?.({ durationMs: dur, cancelled: true });
      return;
    }
    const dur = recorder.durationMs;
    const blob = await recorder.stop();
    onRecordingEnd?.({ durationMs: dur, cancelled: false });
    if (!blob) return;
    recorder.setUploading(true);
    try {
      await onCaptured(blob);
    } finally {
      recorder.setUploading(false);
    }
  };

  const isRecording = recorder.state === "recording";
  const isUploading = recorder.state === "uploading";

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled || isUploading}
        aria-label={isRecording ? "Release to send, slide left to cancel" : "Hold to record voice message"}
        className={cn(
          "inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors",
          "select-none touch-none",
          isRecording
            ? willCancel
              ? "bg-destructive text-destructive-foreground"
              : "bg-destructive/80 text-destructive-foreground animate-pulse"
            : "bg-primary text-primary-foreground hover:bg-primary/90",
          disabled && "opacity-50 cursor-not-allowed",
        )}
        onTouchStart={(e) => handleStart(e.touches[0].clientX)}
        onTouchMove={(e) => handleMove(e.touches[0].clientX)}
        onTouchEnd={handleEnd}
        onTouchCancel={() => {
          if (recorder.state === "recording") {
            const dur = recorder.durationMs;
            recorder.cancel();
            onRecordingEnd?.({ durationMs: dur, cancelled: true });
          }
        }}
        onMouseDown={(e) => handleStart(e.clientX)}
        onMouseMove={(e) => handleMove(e.clientX)}
        onMouseUp={handleEnd}
        onMouseLeave={() => {
          if (recorder.state === "recording") {
            const dur = recorder.durationMs;
            recorder.cancel();
            onRecordingEnd?.({ durationMs: dur, cancelled: true });
          }
        }}
      >
        {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />}
      </button>

      {isRecording && (
        <div
          className={cn(
            "absolute -top-9 right-0 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-xs shadow-sm",
            willCancel ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {formatDuration(recorder.durationMs)} ·{" "}
          {willCancel ? "← Release to cancel" : "← slide to cancel"}
        </div>
      )}
    </div>
  );
}
