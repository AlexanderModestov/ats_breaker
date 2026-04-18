// frontend/src/lib/posthog.ts
"use client";

import posthog from "posthog-js";

let initialized = false;

export function initPostHog(): void {
  if (initialized) return;
  if (typeof window === "undefined") return;

  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  const host = process.env.NEXT_PUBLIC_POSTHOG_HOST;
  if (!key) return; // silently disabled when no key (e.g. local dev without a key)

  posthog.init(key, {
    api_host: host,
    persistence: "memory", // cookieless until signin — see PostHogProvider
    capture_pageview: false, // we emit $pageview manually for App Router navigation
    capture_pageleave: true,
    autocapture: true,
    disable_session_recording: true,
    loaded: (ph) => {
      if (process.env.NODE_ENV === "development") {
        ph.debug();
      }
    },
  });

  initialized = true;
}

export function isPostHogEnabled(): boolean {
  return initialized;
}

export { posthog };
