"use client";

import { useState, useEffect } from "react";
import { getTelegramUserId, isTelegramMiniApp } from "@/lib/telegram";
import { linkTelegramId } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

const PENDING_TG_ID_KEY = "pending_tg_id";
const LINKED_KEY = "tg_linked";

export function DebugTelegramBanner() {
  const { isAuthenticated, loading } = useAuth();
  const [status, setStatus] = useState<string>("idle");
  const [tgAppearedAt, setTgAppearedAt] = useState<string>("checking...");
  const [scriptSrc, setScriptSrc] = useState<string>("?");
  const [fetchProbe, setFetchProbe] = useState<string>("?");
  const [apiProbe, setApiProbe] = useState<string>("?");
  const [authedProbe, setAuthedProbe] = useState<string>("?");
  const [postProbe, setPostProbe] = useState<string>("?");
  const [linkProbeNoAuth, setLinkProbeNoAuth] = useState<string>("?");
  const [cspViolation, setCspViolation] = useState<string>("none");

  const apiBase =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

  useEffect(() => {
    const tag = document.querySelector(
      'script[src*="telegram-web-app"]'
    ) as HTMLScriptElement | null;
    setScriptSrc(tag?.src ?? "(not found)");

    // CSP violation listener
    const cspHandler = (e: SecurityPolicyViolationEvent) => {
      setCspViolation(
        `${e.effectiveDirective} blocked ${e.blockedURI} (policy: ${e.originalPolicy.slice(0, 100)})`
      );
    };
    document.addEventListener("securitypolicyviolation", cspHandler);

    // Fetch probe for Telegram SDK
    fetch("https://telegram.org/js/telegram-web-app.js", { method: "GET" })
      .then((r) => setFetchProbe(`${r.status} ${r.statusText} (len=${r.headers.get("content-length") ?? "?"})`))
      .catch((e) => setFetchProbe("FAIL: " + (e instanceof Error ? e.message : String(e))));

    // Fetch probe for backend health (simple request, no preflight)
    fetch(`${apiBase}/health`)
      .then((r) => setApiProbe(`${r.status} ${r.statusText}`))
      .catch((e) => setApiProbe("FAIL: " + (e instanceof Error ? e.message : String(e))));

    // Fetch probe WITH Authorization header — triggers CORS preflight.
    fetch(`${apiBase}/health`, {
      headers: { Authorization: "Bearer probe" },
    })
      .then((r) => setAuthedProbe(`${r.status} ${r.statusText}`))
      .catch((e) => setAuthedProbe("FAIL: " + (e instanceof Error ? e.message : String(e))));

    // POST probe to a known endpoint — expect 405 Method Not Allowed.
    // "FAIL: Failed to fetch" → POST requests are blocked generally.
    fetch(`${apiBase}/health`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ probe: true }),
    })
      .then((r) => setPostProbe(`${r.status} ${r.statusText}`))
      .catch((e) => setPostProbe("FAIL: " + (e instanceof Error ? e.message : String(e))));

    // POST to /auth/telegram/link without auth — expect 401.
    // "FAIL: Failed to fetch" → route missing/blocked even at CORS level.
    fetch(`${apiBase}/auth/telegram/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ telegram_id: 0 }),
    })
      .then((r) => setLinkProbeNoAuth(`${r.status} ${r.statusText}`))
      .catch((e) => setLinkProbeNoAuth("FAIL: " + (e instanceof Error ? e.message : String(e))));

    if ((window as any).Telegram) {
      setTgAppearedAt("0ms (already)");
      return;
    }
    const start = Date.now();
    const iv = setInterval(() => {
      if ((window as any).Telegram) {
        setTgAppearedAt(`${Date.now() - start}ms`);
        clearInterval(iv);
      }
    }, 100);
    const to = setTimeout(() => {
      clearInterval(iv);
      setTgAppearedAt((prev) =>
        prev === "checking..." ? "NEVER (5s timeout)" : prev
      );
    }, 5000);
    return () => {
      clearInterval(iv);
      clearTimeout(to);
      document.removeEventListener("securitypolicyviolation", cspHandler);
    };
  }, []);

  async function loadScriptManually() {
    setStatus("injecting script...");
    const s = document.createElement("script");
    s.src = "https://telegram.org/js/telegram-web-app.js";
    s.onload = () => {
      setStatus(
        `script onload fired. Telegram now: ${typeof (window as any).Telegram}`
      );
    };
    s.onerror = (e) => {
      setStatus("script ERROR: " + JSON.stringify(e));
    };
    document.head.appendChild(s);
  }

  const w = typeof window !== "undefined" ? (window as any) : null;
  const twa = w?.Telegram?.WebApp ?? null;
  const hasTelegramObj = typeof w?.Telegram !== "undefined";
  const hasWebviewProxy = typeof w?.TelegramWebviewProxy !== "undefined";
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
  const scriptPresent =
    typeof document !== "undefined"
      ? !!document.querySelector('script[src*="telegram-web-app"]')
      : false;
  const locationHref = typeof window !== "undefined" ? window.location.href : "-";
  const locationHash = typeof window !== "undefined" ? window.location.hash : "-";
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "-";

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
scriptTagPresent: ${scriptPresent}
scriptSrc: ${scriptSrc}
tgAppearedAt: ${tgAppearedAt}
fetchProbe (tg): ${fetchProbe}
apiBase: ${apiBase}
apiProbe (simple GET): ${apiProbe}
apiProbe (GET+Auth, preflight): ${authedProbe}
apiProbe (POST /health): ${postProbe}
apiProbe (POST /link no-auth): ${linkProbeNoAuth}
cspViolation: ${cspViolation}
typeof Telegram: ${hasTelegramObj}
TelegramWebviewProxy: ${hasWebviewProxy}
platform: ${platform}
version: ${version}
isMiniApp: ${isMini}
liveId: ${liveId}
stashed: ${stashed}
linked: ${linked}
close fn: ${hasCloseFn}
hash: ${locationHash || "(empty)"}
href: ${locationHref}
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
        <button
          onClick={loadScriptManually}
          style={{ padding: "4px 8px", background: "#ff0", color: "#000", border: 0 }}
        >
          Load TG script now
        </button>
      </div>
    </div>
  );
}
