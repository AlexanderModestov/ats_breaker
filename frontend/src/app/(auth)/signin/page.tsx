"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { motion } from "@/components/motion";
import { getTelegramUserId, isTelegramIOS, isTelegramMiniApp } from "@/lib/telegram";
import { getSupabaseClient } from "@/lib/supabase";
import { linkTelegramId } from "@/lib/api";
import { useAnalytics } from "@/hooks/useAnalytics";
import { LINKED_KEY } from "@/hooks/useLinkTelegram";

const PENDING_TG_ID_KEY = "pending_tg_id";

export default function LoginPage() {
  const router = useRouter();
  const { isAuthenticated, loading, signInWithGoogle } = useAuth();
  const { track } = useAnalytics();

  useEffect(() => {
    if (loading || !isAuthenticated) return;

    const fromMiniApp = getTelegramUserId();
    const fromUrl = (() => {
      const v = new URLSearchParams(window.location.search).get("tg");
      return v ? Number(v) : null;
    })();
    const fromStorage = (() => {
      const v = localStorage.getItem(PENDING_TG_ID_KEY);
      return v ? Number(v) : null;
    })();
    const tgId = fromMiniApp ?? fromUrl ?? fromStorage;
    // ?tg=… is only set by signInWithGoogle's redirectTo, so its presence
    // distinguishes a fresh post-OAuth landing from an auth-state rehydrate
    // that bounced an already-signed-in user through /signin (e.g. from
    // /coach). Only the former should close the WebApp back to the bot.
    const isPostOAuth = fromUrl !== null;

    if (tgId && Number.isFinite(tgId)) {
      linkTelegramId(tgId)
        .then(() => {
          sessionStorage.setItem(LINKED_KEY, "1");
          localStorage.removeItem(PENDING_TG_ID_KEY);
          window.history.replaceState({}, "", "/signin");
          if (isPostOAuth) {
            if (isTelegramMiniApp()) {
              // Android WebApp callback: OAuth completed inside Telegram, just close.
              (window as any).Telegram?.WebApp?.close();
            } else {
              // Safari callback after iOS OAuth hop: deep-link back to the bot.
              const botUsername = process.env.NEXT_PUBLIC_TG_BOT_USERNAME;
              if (botUsername) {
                window.location.href = `tg://resolve?domain=${botUsername}`;
                // Fallback if tg:// doesn't resolve (e.g. Telegram not installed).
                setTimeout(() => {
                  window.location.href = `https://t.me/${botUsername}`;
                }, 1500);
              }
            }
          }
        })
        .catch((err) => {
          console.error("[signin] Failed to link Telegram ID:", err);
        });
    }
    router.push("/optimize");
  }, [isAuthenticated, loading, router]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-3"
        >
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <span className="text-sm text-muted-foreground">Loading...</span>
        </motion.div>
      </div>
    );
  }

  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{
        backgroundColor: "#fafafa",
        backgroundImage: "radial-gradient(circle, #e4e4e7 1px, transparent 1px)",
        backgroundSize: "20px 20px",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
        className="w-full max-w-sm rounded-lg border border-zinc-200 bg-white p-8"
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-violet-700">
            <span className="text-sm font-bold text-white">HR</span>
          </div>
          <span className="text-xl font-semibold tracking-tight text-zinc-900">Breaker</span>
        </div>

        {/* Heading */}
        <div className="mt-6 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-zinc-900">Welcome back</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Sign in to continue optimizing your resume.
          </p>
        </div>

        {/* Google button */}
        <div className="mt-8">
          <Button
            className="w-full gap-3 border border-zinc-200 bg-white py-5 text-sm font-medium text-zinc-700 shadow-none hover:bg-zinc-50"
            variant="outline"
            size="lg"
            onClick={async () => {
              const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
              if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));

              const redirectTo = tgId
                ? `${window.location.origin}/signin?tg=${tgId}`
                : `${window.location.origin}/signin`;

              track("signin_started", { method: "google" });

              if (isTelegramMiniApp() && isTelegramIOS()) {
                // iOS Telegram WebApp uses WKWebView, which Google blocks for
                // OAuth (Error 403: disallowed_useragent). Open the auth URL
                // in Safari instead.
                const supabase = getSupabaseClient();
                const { data, error } = await supabase.auth.signInWithOAuth({
                  provider: "google",
                  options: { redirectTo, skipBrowserRedirect: true },
                });
                if (error || !data?.url) {
                  track("signin_failed", {
                    method: "google",
                    error: error?.message ?? "no_url",
                  });
                  return;
                }
                const wa = (window as any).Telegram?.WebApp;
                wa?.openLink(data.url, { try_instant_view: false });
                wa?.close();
                return;
              }

              try {
                await signInWithGoogle(redirectTo);
              } catch (err) {
                track("signin_failed", {
                  method: "google",
                  error: err instanceof Error ? err.message : String(err),
                });
              }
            }}
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </Button>
        </div>

        {/* Fine print */}
        <p className="mt-6 text-center text-xs text-zinc-400">
          By continuing, you agree to our Terms and Privacy Policy.
        </p>
      </motion.div>
    </div>
  );
}
