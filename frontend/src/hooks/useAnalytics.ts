// frontend/src/hooks/useAnalytics.ts
"use client";

import { useRef } from "react";
import { posthog } from "@/lib/posthog";

export type AnalyticsEvent =
  | "signin_started"
  | "signin_completed"
  | "signin_failed"
  | "resume_uploaded"
  | "job_provided"
  | "optimization_started"
  | "optimization_completed"
  | "optimization_failed"
  | "pdf_downloaded"
  | "pricing_viewed"
  | "pdf_history_viewed"
  | "coach_voice_recording_started"
  | "coach_voice_recording_completed"
  | "coach_voice_error";

type TrackFn = (event: AnalyticsEvent, props?: Record<string, unknown>) => void;

export function useAnalytics(): { track: TrackFn } {
  // Stable reference across renders so callers can safely pass `track` into
  // useEffect deps without re-firing on unrelated re-renders.
  const trackRef = useRef<TrackFn>((event, props) => {
    try {
      posthog.capture(event, props);
    } catch {
      // PostHog may be uninitialized (no key in env); swallow — never break UX.
    }
  });
  return { track: trackRef.current };
}
