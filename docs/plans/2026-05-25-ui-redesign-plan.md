# UI Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign HR-Breaker's frontend to a minimal, professional aesthetic inspired by Linear/Clerk/Resend — Geist font, violet accent, zinc palette, sidebar nav, dark hero.

**Architecture:** All changes are in `frontend/src/`. No backend changes. CSS variables drive the token system; Tailwind utility classes handle layout. The sidebar replaces the top navbar in the protected layout; the landing page gets a full dark hero with light content sections beneath.

**Tech Stack:** Next.js 15, Tailwind CSS, Framer Motion, shadcn/ui components, `next/font/google` (Geist)

**Worktree:** `.worktrees/ui-redesign`

---

### Task 1: Design system — font, tokens, radius

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/tailwind.config.ts`

**Step 1: Swap font from Inter to Geist in layout.tsx**

Replace lines 1-12 of `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Providers } from "./providers";
import { JsonLd } from "./components/JsonLd";

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
});
```

Replace the body className on line 59:
```tsx
<body className={`${geist.variable} font-sans antialiased`} suppressHydrationWarning>
```

**Step 2: Replace globals.css**

Replace the full contents of `frontend/src/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: 0 0% 100%;
  --foreground: 240 4% 11%;

  --card: 0 0% 98%;
  --card-foreground: 240 4% 11%;

  --popover: 0 0% 100%;
  --popover-foreground: 240 4% 11%;

  /* Primary maps to violet accent */
  --primary: 263 70% 52%;
  --primary-foreground: 0 0% 100%;

  --secondary: 240 5% 96%;
  --secondary-foreground: 240 4% 20%;

  --muted: 240 5% 96%;
  --muted-foreground: 240 4% 46%;

  --accent: 240 5% 96%;
  --accent-foreground: 240 4% 11%;

  --destructive: 0 72% 51%;
  --destructive-foreground: 0 0% 100%;

  --success: 152 60% 42%;
  --success-foreground: 0 0% 100%;

  --warning: 38 92% 50%;
  --warning-foreground: 0 0% 100%;

  --border: 240 6% 90%;
  --input: 240 6% 90%;
  --ring: 263 70% 52%;

  --radius: 0.5rem;
}

@layer base {
  * {
    @apply border-border;
  }

  html {
    scroll-behavior: smooth;
  }

  body {
    @apply bg-background text-foreground antialiased;
    overflow-x: hidden;
  }

  *:focus-visible {
    @apply outline-none ring-2 ring-ring ring-offset-2 ring-offset-background;
    transition: box-shadow 0.15s ease;
  }
}

@layer components {
  .shimmer {
    background: linear-gradient(
      90deg,
      hsl(var(--muted)) 0%,
      hsl(var(--secondary)) 50%,
      hsl(var(--muted)) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  .page-container {
    @apply mx-auto max-w-5xl px-4 sm:px-6 lg:px-8;
  }
}
```

**Step 3: Update tailwind.config.ts — remove old font import reference, keep structure**

No changes needed to tailwind.config.ts — it already uses `var(--font-sans)` and `var(--radius)` dynamically, so the globals.css changes take effect automatically.

**Step 4: Verify build**

```
cd frontend && npm run build
```

Expected: Build passes. The app will look visually broken at this point (violet primary, different colors) — that is expected. We'll fix each surface in subsequent tasks.

**Step 5: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/src/app/globals.css
git commit -m "feat(redesign): swap to Geist font and update design tokens"
```

---

### Task 2: Sidebar navigation (replace top navbar)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/app/(protected)/layout.tsx`

**Step 1: Create Sidebar.tsx**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Sparkles, FileText, MessageCircle, History, Settings, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/optimize", label: "Optimize", icon: Sparkles },
  { href: "/cvs", label: "CVs", icon: FileText },
  { href: "/coach", label: "Coach", icon: MessageCircle },
  { href: "/history", label: "History", icon: History },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:z-50 lg:w-56 lg:border-r lg:border-border lg:bg-background">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2.5 px-5 border-b border-border">
          <Link href="/optimize" className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
              <span className="text-xs font-bold text-primary-foreground">HR</span>
            </div>
            <span className="text-sm font-semibold tracking-tight">Breaker</span>
          </Link>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href}>
                <div
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors relative",
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  )}
                >
                  {isActive && (
                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-primary" />
                  )}
                  <Icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* User section */}
        <div className="border-t border-border px-3 py-4 space-y-0.5">
          <Link href="/settings">
            <div className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors">
              <Settings className="h-4 w-4 shrink-0" />
              Settings
            </div>
          </Link>
          <div className="flex items-center gap-2.5 rounded-md px-3 py-2">
            <div className="flex-1 min-w-0">
              <p className="text-xs text-muted-foreground truncate">{user?.email?.split("@")[0]}</p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => signOut()}
              className="h-7 w-7 text-muted-foreground hover:text-foreground shrink-0"
            >
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </aside>

      {/* Mobile bottom tab bar */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background/95 backdrop-blur-sm">
        <div className="flex items-center justify-around h-16 px-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="flex-1">
                <div className={cn(
                  "flex flex-col items-center gap-1 py-2 text-xs font-medium transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground"
                )}>
                  <Icon className="h-5 w-5" />
                  {item.label}
                </div>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
```

**Step 2: Update protected layout to use Sidebar**

Replace `frontend/src/app/(protected)/layout.tsx` content:

```tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { useLinkTelegram } from "@/hooks/useLinkTelegram";
import { useTelegramAutoLogin } from "@/hooks/useTelegramAutoLogin";
import { Sidebar } from "@/components/Sidebar";
import { motion } from "framer-motion";
import { PricingModalProvider } from "@/context/PricingModalContext";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, loading } = useAuth();
  const { attempting } = useTelegramAutoLogin();

  useLinkTelegram();

  useEffect(() => {
    if (!loading && !attempting && !isAuthenticated) {
      router.push("/signin");
    }
  }, [isAuthenticated, loading, attempting, router]);

  if (loading || attempting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="flex flex-col items-center gap-4"
        >
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </motion.div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <PricingModalProvider>
      <div className="min-h-screen bg-background">
        <Sidebar />
        <motion.main
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="lg:pl-56 pb-16 lg:pb-0"
        >
          <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
            {children}
          </div>
        </motion.main>
      </div>
    </PricingModalProvider>
  );
}
```

**Step 3: Verify build**

```
cd frontend && npm run build
```

Expected: Build passes. Sidebar should be functional in dev.

**Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx "frontend/src/app/(protected)/layout.tsx"
git commit -m "feat(redesign): replace top navbar with sidebar navigation"
```

---

### Task 3: Auth screen — centered card on dot-grid

**Files:**
- Modify: `frontend/src/app/(auth)/signin/page.tsx`

**Step 1: Replace signin page layout**

Keep all existing logic (useEffect, Telegram handling, signInWithGoogle call) intact. Only change the returned JSX. Replace from `return (` to end of file with:

```tsx
  return (
    <div
      className="flex min-h-screen items-center justify-center px-4"
      style={{
        backgroundColor: "hsl(240 5% 96%)",
        backgroundImage: "radial-gradient(hsl(240 6% 90%) 1px, transparent 1px)",
        backgroundSize: "20px 20px",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm rounded-lg border border-border bg-white p-8 shadow-sm space-y-6"
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <span className="text-xs font-bold text-primary-foreground">HR</span>
          </div>
          <span className="text-base font-semibold tracking-tight">Breaker</span>
        </div>

        {/* Heading */}
        <div className="text-center space-y-1.5">
          <h1 className="text-2xl font-bold tracking-tight">Welcome back</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to continue optimizing your resume.
          </p>
        </div>

        {/* Google button */}
        <Button
          className="w-full gap-3 bg-white text-zinc-900 border border-border hover:bg-zinc-50 font-medium"
          size="lg"
          onClick={async () => {
            const tgId = isTelegramMiniApp() ? getTelegramUserId() : null;
            if (tgId) localStorage.setItem(PENDING_TG_ID_KEY, String(tgId));

            const redirectTo = tgId
              ? `${window.location.origin}/signin?tg=${tgId}`
              : `${window.location.origin}/signin`;

            track("signin_started", { method: "google" });

            if (isTelegramMiniApp() && isTelegramIOS()) {
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
          <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Continue with Google
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          By continuing, you agree to our Terms and Privacy Policy.
        </p>
      </motion.div>
    </div>
  );
```

Also remove unused imports `ArrowRight`, `FileText`, `Sparkles`, `Target`, and the `features` array from the top of the file.

**Step 2: Verify build**

```
cd frontend && npm run build
```

Expected: Build passes.

**Step 3: Commit**

```bash
git add "frontend/src/app/(auth)/signin/page.tsx"
git commit -m "feat(redesign): centered card auth screen, remove split layout"
```

---

### Task 4: Landing header — transparent → sticky white

**Files:**
- Modify: `frontend/src/app/_components/LandingHeader.tsx`

**Step 1: Update LandingHeader**

Replace the full contents of `frontend/src/app/_components/LandingHeader.tsx`:

```tsx
"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";
import { type Lang } from "../_lib/translations";
import { cn } from "@/lib/utils";

const languages: { code: Lang; label: string }[] = [
  { code: "en", label: "English" },
  { code: "ru", label: "Русский" },
];

export function LandingHeader() {
  const { lang, setLang } = useLang();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleScroll() {
      setScrolled(window.scrollY > 20);
    }
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const activeLang = languages.find((l) => l.code === lang)!;

  return (
    <nav
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300",
        scrolled
          ? "bg-white/95 backdrop-blur-sm border-b border-zinc-200"
          : "bg-transparent"
      )}
    >
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
            <span className="text-xs font-bold text-primary-foreground">HR</span>
          </div>
          <span className={cn(
            "text-sm font-semibold tracking-tight transition-colors",
            scrolled ? "text-zinc-900" : "text-white"
          )}>
            Breaker
          </span>
        </Link>

        <div className="flex items-center gap-3">
          {/* Language selector */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setOpen(!open)}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors",
                scrolled
                  ? "text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100"
                  : "text-zinc-400 hover:text-white hover:bg-white/10"
              )}
            >
              {activeLang.label}
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"
                className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
                <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {open && (
              <div className="absolute right-0 mt-1 min-w-[140px] rounded-lg border border-zinc-200 bg-white shadow-lg py-1">
                {languages.map((l) => (
                  <button
                    key={l.code}
                    onClick={() => { setLang(l.code); setOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                      l.code === lang
                        ? "font-medium text-zinc-900 bg-zinc-50"
                        : "text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50"
                    }`}
                  >
                    {l.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <Link href="/signin">
            <Button
              variant="ghost"
              size="sm"
              className={cn(
                "transition-colors",
                scrolled ? "text-zinc-600 hover:text-zinc-900" : "text-zinc-300 hover:text-white hover:bg-white/10"
              )}
            >
              {t.nav.login[lang]}
            </Button>
          </Link>

          <Link href="/signin">
            <Button size="sm" className="bg-primary hover:bg-primary/90 text-primary-foreground">
              Get started
            </Button>
          </Link>
        </div>
      </div>
    </nav>
  );
}
```

**Step 2: Verify build**

```
cd frontend && npm run build
```

Expected: Build passes.

**Step 3: Commit**

```bash
git add frontend/src/app/_components/LandingHeader.tsx
git commit -m "feat(redesign): transparent-to-sticky landing header with dual CTAs"
```

---

### Task 5: Landing hero — full dark section

**Files:**
- Modify: `frontend/src/app/_components/HeroSection.tsx`
- Modify: `frontend/src/app/page.tsx` (remove background wrapper so hero is full-bleed)

**Step 1: Replace HeroSection.tsx**

```tsx
"use client";

import Link from "next/link";
import { motion } from "@/components/motion";
import { Button } from "@/components/ui/button";
import { useLang } from "../_lib/LangContext";

export function HeroSection() {
  const { lang } = useLang();

  return (
    <section
      className="relative flex min-h-screen items-center justify-center overflow-hidden"
      style={{ backgroundColor: "#09090B" }}
    >
      {/* Radial violet bloom */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: "radial-gradient(ellipse 80% 50% at 50% 40%, rgba(124,58,237,0.15) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-3xl px-4 text-center sm:px-6">
        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-5xl font-bold tracking-tight text-white sm:text-6xl lg:text-7xl"
          style={{ letterSpacing: "-0.03em" }}
        >
          Transform your resume
          <br />
          for every job posting.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="mt-6 text-lg text-zinc-400"
        >
          AI-powered. ATS-ready. One click.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mt-10 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
        >
          <Link href="/signin">
            <Button size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground px-8 text-base">
              Get started free
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="lg"
            className="text-zinc-300 hover:text-white hover:bg-white/10 px-8 text-base"
            onClick={() => {
              document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            See how it works
          </Button>
        </motion.div>
      </div>
    </section>
  );
}
```

**Step 2: Update page.tsx to allow full-bleed dark hero**

In `frontend/src/app/page.tsx`, change the wrapper div from:
```tsx
<div className="min-h-screen bg-background">
```
to:
```tsx
<div className="min-h-screen">
```

**Step 3: Verify build**

```
cd frontend && npm run build
```

Expected: Build passes.

**Step 4: Commit**

```bash
git add frontend/src/app/_components/HeroSection.tsx frontend/src/app/page.tsx
git commit -m "feat(redesign): full-viewport dark hero with violet bloom"
```

---

### Task 6: Landing footer — dark

**Files:**
- Modify: `frontend/src/app/_components/LandingFooter.tsx`

**Step 1: Replace LandingFooter.tsx**

```tsx
"use client";

import Link from "next/link";
import { useLang } from "../_lib/LangContext";
import { t } from "../_lib/translations";

export function LandingFooter() {
  const { lang } = useLang();

  return (
    <footer style={{ backgroundColor: "#09090B" }}>
      <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
                <span className="text-xs font-bold text-primary-foreground">HR</span>
              </div>
              <span className="text-sm font-semibold tracking-tight text-white">Breaker</span>
            </div>
            <p className="mt-3 text-sm text-zinc-500">
              {t.footer.tagline[lang]}
            </p>
          </div>

          {/* Links */}
          <div className="flex gap-12">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">{t.footer.links[lang]}</h3>
              <ul className="mt-3 space-y-2">
                <li>
                  <a href="#pricing" className="text-sm text-zinc-400 hover:text-white transition-colors">
                    {t.footer.pricing[lang]}
                  </a>
                </li>
                <li>
                  <Link href="/signin" className="text-sm text-zinc-400 hover:text-white transition-colors">
                    {t.footer.login[lang]}
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">{t.footer.legal[lang]}</h3>
              <ul className="mt-3 space-y-2">
                <li><span className="text-sm text-zinc-500">{t.footer.privacy[lang]}</span></li>
                <li><span className="text-sm text-zinc-500">{t.footer.terms[lang]}</span></li>
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-10 border-t border-zinc-800 pt-6">
          <p className="text-center text-xs text-zinc-600">
            {t.footer.copyright[lang]}
          </p>
        </div>
      </div>
    </footer>
  );
}
```

**Step 2: Verify build and commit**

```
cd frontend && npm run build
git add frontend/src/app/_components/LandingFooter.tsx
git commit -m "feat(redesign): dark footer matching hero"
```

---

### Task 7: Landing content sections — restyle to white

**Files:**
- Modify: `frontend/src/app/_components/HowItWorksSection.tsx`
- Modify: `frontend/src/app/_components/FeaturesSection.tsx`
- Modify: `frontend/src/app/_components/PricingSection.tsx`

**Step 1: Add `id="how-it-works"` to HowItWorksSection**

In `HowItWorksSection.tsx`, find the outer `<section` tag and add `id="how-it-works"` to it. This makes the hero "See how it works" scroll target work.

**Step 2: Update PricingSection.tsx — remove ribbon badges, apply violet border to middle card**

In `PricingSection.tsx`, find any element with text "Most Popular" or a ribbon/badge on the highlighted plan. Remove those elements. On the middle/highlighted plan card, replace any gradient background or colored fill with:
```tsx
className="... border-violet-400 bg-violet-50"
```
and ensure the standard cards use `border-zinc-200 bg-white`.

**Step 3: Verify build and commit**

```
cd frontend && npm run build
git add frontend/src/app/_components/HowItWorksSection.tsx frontend/src/app/_components/FeaturesSection.tsx frontend/src/app/_components/PricingSection.tsx
git commit -m "feat(redesign): restyle landing content sections, remove badge decorations"
```

---

### Task 8: Optimize page — restyle app work area

**Files:**
- Modify: `frontend/src/app/(protected)/optimize/page.tsx`
- Modify: `frontend/src/components/QuotaBanner.tsx`

**Step 1: Read QuotaBanner to understand current structure**

Read `frontend/src/components/QuotaBanner.tsx` before editing.

**Step 2: Update QuotaBanner to slim zinc style**

Replace the banner's outer container classes with `bg-zinc-100 text-zinc-600 text-sm rounded-md px-4 py-2.5 flex items-center justify-between`. Remove any alert icons or red coloring. Ensure the upgrade link uses `text-primary font-medium`.

**Step 3: Read full optimize page.tsx**

Read `frontend/src/app/(protected)/optimize/page.tsx` in full before editing.

**Step 4: Restyle optimize page**

The optimize page currently wraps content in `<Card>`. Replace that structure with plain divs using the new design:
- Page heading: `<h1 className="text-xl font-bold tracking-tight">Optimize resume</h1>` at top
- Section label above CV dropdown: `<label className="text-sm font-medium text-muted-foreground">Your resume</label>`
- Section label above job input: `<label className="text-sm font-medium text-muted-foreground">Job posting</label>`
- Optimize button: `className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-medium"` with shimmer on loading
- Wrap whole content in `<div className="space-y-6">`

**Step 5: Verify build and commit**

```
cd frontend && npm run build
git add "frontend/src/app/(protected)/optimize/page.tsx" frontend/src/components/QuotaBanner.tsx
git commit -m "feat(redesign): restyle optimize page work area"
```

---

### Task 9: Pricing — update PricingContent and PricingModal

**Files:**
- Modify: `frontend/src/components/PricingContent.tsx`
- Modify: `frontend/src/components/PricingModal.tsx` (if exists)

**Step 1: Read current files**

Read `frontend/src/components/PricingContent.tsx` in full before editing.

**Step 2: Update PricingContent**

- Add violet eyebrow above heading: `<p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">Pricing</p>`
- Update heading to: `<h2 className="text-4xl font-bold tracking-tight" style={{letterSpacing: "-0.03em"}}>Simple, transparent pricing.</h2>`
- Add subline: `<p className="mt-3 text-muted-foreground">Start free. Upgrade when you're ready.</p>`
- On the highlighted "Job Hunter" card: replace any gradient/colored background with `className="border border-violet-400 bg-violet-50"`. Remove any "Most Popular" badge/ribbon.
- On other cards: `className="border border-border bg-white"`

**Step 3: Read and update PricingModal**

Read `frontend/src/components/PricingModal.tsx`. Update the Dialog overlay to use `bg-black/60` without backdrop-blur. Update modal header to show "Upgrade your plan" with a close X button.

**Step 4: Verify build and commit**

```
cd frontend && npm run build
git add frontend/src/components/PricingContent.tsx frontend/src/components/PricingModal.tsx
git commit -m "feat(redesign): update pricing cards and modal to new design"
```

---

### Task 10: Final build verification

**Step 1: Full build**

```
cd frontend && npm run build
```

Expected: Build passes with 0 TypeScript errors.

**Step 2: Run dev server and do a visual walkthrough**

```
cd frontend && npm run dev
```

Check each surface:
- [ ] Landing: dark hero visible at `/`
- [ ] Landing header becomes white/blurred on scroll
- [ ] Auth: centered card on dot-grid at `/signin`
- [ ] App: sidebar visible at `/optimize` on desktop, bottom tabs on mobile
- [ ] Pricing: violet-bordered middle card, no badges
- [ ] Font is Geist throughout

**Step 3: Final commit if any fixes needed, then done**
