"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import type { User } from "@supabase/supabase-js";
import { getSupabaseClient } from "@/lib/supabase";
import { initPostHog, posthog } from "@/lib/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const hadSessionRef = useRef(false);

  // Init + Supabase auth subscription (one-shot on mount).
  useEffect(() => {
    initPostHog();
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;

    const supabase = getSupabaseClient();

    // Pick up an existing session at load time (e.g. refresh while logged in).
    // Marks hadSessionRef so a later SIGNED_IN on session restore doesn't
    // double-fire signin_completed.
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        hadSessionRef.current = true;
        identifyUser(session.user);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session?.user) {
        const wasAnonymous = !hadSessionRef.current;
        hadSessionRef.current = true;
        identifyUser(session.user);
        if (wasAnonymous) {
          // Fire only on the anonymous → user transition. Supabase re-emits
          // SIGNED_IN on session restore in some 2.x versions; this guard
          // keeps signin_completed exactly-once per actual sign-in.
          posthog.capture("signin_completed");
        }
      } else if (event === "SIGNED_OUT") {
        hadSessionRef.current = false;
        // Swap persistence back to memory BEFORE reset so reset clears the
        // right backend and no stale cookies linger.
        posthog.set_config({ persistence: "memory" });
        posthog.reset();
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  // Emit $pageview on client-side navigation.
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !pathname) return;
    const qs = searchParams?.toString();
    const url = qs ? `${pathname}?${qs}` : pathname;
    posthog.capture("$pageview", { $current_url: url });
  }, [pathname, searchParams]);

  return <>{children}</>;
}

function identifyUser(user: User) {
  // Persistence MUST switch before identify() so the new distinct_id is
  // written to the persistent backend, not memory.
  posthog.set_config({ persistence: "localStorage+cookie" });
  const provider =
    (user.app_metadata as { provider?: string } | undefined)?.provider ??
    user.identities?.[0]?.provider ??
    "unknown";
  posthog.identify(user.id, {
    email: user.email,
    created_at: user.created_at,
    auth_provider: provider,
  });
}
