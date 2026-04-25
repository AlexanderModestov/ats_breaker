"use client";

import { useEffect } from "react";
import { getTelegramUserId, isTelegramMiniApp } from "@/lib/telegram";
import { linkTelegramId } from "@/lib/api";
import { useAuth } from "./useAuth";

export const LINKED_KEY = "tg_linked";
const PENDING_TG_ID_KEY = "pending_tg_id";

export function useLinkTelegram() {
  const { isAuthenticated, loading } = useAuth();

  useEffect(() => {
    if (loading || !isAuthenticated) return;
    if (!isTelegramMiniApp()) return;
    if (sessionStorage.getItem(LINKED_KEY) === "1") return;

    const live = getTelegramUserId();
    const stashed = Number(localStorage.getItem(PENDING_TG_ID_KEY)) || null;
    const telegramId = live ?? stashed;

    if (!telegramId) return;

    linkTelegramId(telegramId)
      .then(() => {
        sessionStorage.setItem(LINKED_KEY, "1");
        localStorage.removeItem(PENDING_TG_ID_KEY);
        (window as any).Telegram?.WebApp?.close();
      })
      .catch(() => {
        // Non-fatal: user is signed in; bot will show the sign-in button again next time.
      });
  }, [isAuthenticated, loading]);
}
