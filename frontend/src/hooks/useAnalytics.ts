// frontend/src/hooks/useAnalytics.ts
"use client";

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
  | "pdf_history_viewed";

export function useAnalytics() {
  return {
    track: (event: AnalyticsEvent, props?: Record<string, unknown>) => {
      try {
        posthog.capture(event, props);
      } catch {
        // PostHog may be uninitialized (no key in env); swallow — never break UX.
      }
    },
  };
}
