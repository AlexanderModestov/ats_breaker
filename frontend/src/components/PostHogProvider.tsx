"use client";

import { useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { getSupabaseClient } from "@/lib/supabase";
import { initPostHog, posthog } from "@/lib/posthog";

export function PostHogProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Init + Supabase auth subscription (one-shot on mount).
  useEffect(() => {
    initPostHog();
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;

    const supabase = getSupabaseClient();

    // Pick up an existing session at load time (e.g. refresh while logged in).
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        identifyUser(session.user.id, session.user.email, session.user.created_at);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_IN" && session?.user) {
        identifyUser(session.user.id, session.user.email, session.user.created_at);
        posthog.capture("signin_completed");
      } else if (event === "SIGNED_OUT") {
        posthog.reset();
        posthog.set_config({ persistence: "memory" });
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

function identifyUser(
  userId: string,
  email: string | undefined,
  createdAt: string | undefined
) {
  // Switch to persistent storage now that the user has a logged-in session
  // (ToS accepted → consent covers analytics cookies).
  posthog.set_config({ persistence: "localStorage+cookie" });
  posthog.identify(userId, {
    email,
    created_at: createdAt,
    auth_provider: "google",
  });
}
