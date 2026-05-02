"use client";

import { useEffect, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase";
import { isTelegramMiniApp, getTelegramWebApp } from "@/lib/telegram";
import { exchangeTelegramInitData } from "@/lib/api";
import { useAuth } from "./useAuth";

const TRIED_KEY = "tg_auto_login_tried";

/**
 * In a Telegram Mini App, if the user is not signed in but their telegram_id
 * is already linked to a Supabase account, exchange the signed initData for a
 * magic-link token_hash and complete sign-in via verifyOtp. Silent fallback to
 * regular /signin (Google OAuth) on any failure or for unlinked users.
 */
export function useTelegramAutoLogin(): { attempting: boolean } {
  const { isAuthenticated, loading } = useAuth();
  const [attempting, setAttempting] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    if (!isTelegramMiniApp()) return false;
    if (sessionStorage.getItem(TRIED_KEY) === "1") return false;
    return true;
  });

  useEffect(() => {
    if (loading) return;
    if (isAuthenticated) {
      setAttempting(false);
      return;
    }
    if (!isTelegramMiniApp()) {
      setAttempting(false);
      return;
    }
    if (sessionStorage.getItem(TRIED_KEY) === "1") {
      setAttempting(false);
      return;
    }

    const initData = getTelegramWebApp()?.initData;
    if (!initData) {
      sessionStorage.setItem(TRIED_KEY, "1");
      setAttempting(false);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const { token_hash, email } = await exchangeTelegramInitData(initData);
        const supabase = getSupabaseClient();
        await supabase.auth.verifyOtp({
          token_hash,
          type: "magiclink",
          email,
        });
        // useAuth's onAuthStateChange will pick up the new session.
      } catch {
        // Silent fallback: ProtectedLayout will redirect to /signin.
      } finally {
        if (!cancelled) {
          sessionStorage.setItem(TRIED_KEY, "1");
          setAttempting(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loading, isAuthenticated]);

  return { attempting };
}
