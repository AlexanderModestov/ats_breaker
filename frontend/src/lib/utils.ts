import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Coarse pointer + narrow viewport — best proxy we have for "phone/tablet
 * in portrait". SSR-safe (returns false when window is missing).
 */
export function isMobileDevice(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(pointer: coarse)").matches && window.innerWidth < 768;
}

/**
 * Whether the browser can record audio in a MIME type Gemini accepts.
 * We try opus first; fall back to mp4 (iOS Safari).
 */
export function pickRecorderMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
  return null;
}

export function isVoiceRecordingSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    pickRecorderMimeType() !== null
  );
}
