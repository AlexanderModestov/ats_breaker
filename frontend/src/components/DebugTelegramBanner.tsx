"use client";

import { useState } from "react";
import { getTelegramUserId, isTelegramMiniApp } from "@/lib/telegram";
import { linkTelegramId } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

const PENDING_TG_ID_KEY = "pending_tg_id";
const LINKED_KEY = "tg_linked";

export function DebugTelegramBanner() {
  const { isAuthenticated, loading } = useAuth();
  const [status, setStatus] = useState<string>("idle");

  const twa =
    typeof window !== "undefined" ? (window as any).Telegram?.WebApp : null;
  const platform = twa?.platform ?? "(no Telegram.WebApp)";
  const version = twa?.version ?? "-";
  const isMini = isTelegramMiniApp();
  const liveId = getTelegramUserId();
  const stashed =
    typeof window !== "undefined"
      ? localStorage.getItem(PENDING_TG_ID_KEY)
      : null;
  const linked =
    typeof window !== "undefined"
      ? sessionStorage.getItem(LINKED_KEY)
      : null;
  const hasCloseFn = typeof twa?.close === "function";

  async function tryLink() {
    const id = liveId ?? (stashed ? Number(stashed) : null);
    if (!id) {
      setStatus("no id available");
      return;
    }
    setStatus(`linking ${id}...`);
    try {
      await linkTelegramId(id);
      sessionStorage.setItem(LINKED_KEY, "1");
      localStorage.removeItem(PENDING_TG_ID_KEY);
      setStatus(`linked OK (${id})`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus("link FAIL: " + msg);
    }
  }

  function tryClose() {
    try {
      twa?.close?.();
      setStatus("close() called");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus("close FAIL: " + msg);
    }
  }

  function clearStash() {
    localStorage.removeItem(PENDING_TG_ID_KEY);
    sessionStorage.removeItem(LINKED_KEY);
    setStatus("cleared");
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 99999,
        background: "#000",
        color: "#0f0",
        padding: 8,
        fontFamily: "monospace",
        fontSize: 11,
        lineHeight: 1.35,
        whiteSpace: "pre-wrap",
        borderBottom: "2px solid #0f0",
      }}
    >
      {`DEBUG TG BANNER
isAuth: ${isAuthenticated}
loading: ${loading}
platform: ${platform}
version: ${version}
isMiniApp: ${isMini}
liveId: ${liveId}
stashed: ${stashed}
linked: ${linked}
close fn: ${hasCloseFn}
status: ${status}`}
      <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
        <button
          onClick={tryLink}
          style={{ padding: "4px 8px", background: "#0f0", color: "#000", border: 0 }}
        >
          Link now
        </button>
        <button
          onClick={tryClose}
          style={{ padding: "4px 8px", background: "#0f0", color: "#000", border: 0 }}
        >
          Close WebApp
        </button>
        <button
          onClick={clearStash}
          style={{ padding: "4px 8px", background: "#555", color: "#fff", border: 0 }}
        >
          Clear storage
        </button>
      </div>
    </div>
  );
}
