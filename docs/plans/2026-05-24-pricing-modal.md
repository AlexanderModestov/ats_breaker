# Pricing Modal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace navigation to `/pricing` from inside the app with an in-app modal so users never lose their context.

**Architecture:** Extract `PricingContent` from `pricing/page.tsx`, wrap it in a `<Dialog>` controlled by a React context. The `/pricing` route stays intact for direct URL access. All 4 in-app entry points call `usePricingModal().open()` instead of navigating.

**Tech Stack:** Next.js 14 / TypeScript, shadcn/ui `Dialog`, React Context

---

## Task 1: Extract PricingContent component

**Files:**
- Create: `frontend/src/components/PricingContent.tsx`

Extract the entire body of `PricingPage` from `frontend/src/app/pricing/page.tsx` into a new component. Add one optional prop.

**Step 1: Create the file**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { useAuth } from "@/hooks/useAuth";
import {
  useSubscription,
  useCheckout,
  useBillingPortal,
  useUpgradePreview,
  useUpgrade,
} from "@/hooks/useSubscription";
import { useAnalytics } from "@/hooks/useAnalytics";
import { TIER_LABEL, TIER_RANK, type Tier } from "@/lib/tiers";

type Feature = string | { label: string; soon?: boolean };

type Plan = {
  tier: Tier;
  price: string;
  tagline: string;
  features: Feature[];
  highlighted?: boolean;
};

const PLANS: Plan[] = [
  {
    tier: "free",
    price: "Free",
    tagline: "Try it out",
    features: [
      "3 resume optimizations / week",
      "Basic ATS optimization",
      "Keyword highlights",
      "AI Interview Prep (limited)",
      "PDF download",
    ],
  },
  {
    tier: "job_hunter",
    price: "€19/month",
    tagline: "Get more interviews",
    features: [
      "Everything in Starter +",
      "Unlimited resume optimizations",
      "Full ATS score",
      "Missing keywords & improvements",
      "Multiple formats (PDF, DOCX)",
      "Version history",
    ],
    highlighted: true,
  },
  {
    tier: "offer_mode",
    price: "€29/month",
    tagline: "Get the offer",
    features: [
      "Everything in Job Hunter +",
      "AI interview prep",
      "Answers to common questions",
      "STAR-structured responses",
      "Personalized feedback",
      "Gap analysis",
      { label: "Cover letter generator", soon: true },
    ],
  },
];

function formatAmount(amountCents: number, currency: string) {
  return new Intl.NumberFormat("en-EU", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(amountCents / 100);
}

type Props = {
  onClose?: () => void;
};

export function PricingContent({ onClose }: Props) {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const { data: sub } = useSubscription();
  const checkout = useCheckout();
  const portal = useBillingPortal();
  const upgrade = useUpgrade();
  const { track } = useAnalytics();

  const [pendingUpgrade, setPendingUpgrade] = useState<Exclude<Tier, "free"> | null>(null);

  const preview = useUpgradePreview(pendingUpgrade);

  const handleUpgradeConfirm = () => {
    if (!pendingUpgrade) return;
    upgrade.mutate(pendingUpgrade, {
      onSuccess: () => {
        setPendingUpgrade(null);
        if (onClose) {
          onClose();
        } else {
          router.push("/settings");
        }
      },
    });
  };

  type CtaState = { label: string; onClick: () => void; disabled: boolean };

  const ctaFor = (planTier: Tier): CtaState => {
    if (!isAuthenticated) {
      return {
        label: "Sign up",
        onClick: () => router.push("/signin?redirect=/pricing"),
        disabled: authLoading,
      };
    }

    const current: Tier = sub?.tier ?? "free";

    if (planTier === current) {
      if (current === "free") {
        return { label: "Current plan", onClick: () => {}, disabled: true };
      }
      return {
        label: "Manage subscription",
        onClick: () => portal.mutate(),
        disabled: portal.isPending,
      };
    }

    if (planTier === "free") {
      return {
        label: "Downgrade",
        onClick: () => portal.mutate(),
        disabled: portal.isPending,
      };
    }

    if (current === "free") {
      return {
        label: "Subscribe",
        onClick: () => checkout.mutate(planTier as Exclude<Tier, "free">),
        disabled: checkout.isPending,
      };
    }

    if (TIER_RANK[planTier] < TIER_RANK[current]) {
      return {
        label: "Downgrade",
        onClick: () => portal.mutate(),
        disabled: portal.isPending,
      };
    }
    return {
      label: "Upgrade",
      onClick: () => setPendingUpgrade(planTier as Exclude<Tier, "free">),
      disabled: false,
    };
  };

  return (
    <>
      <div className="mx-auto max-w-2xl text-center">
        <h1 className="text-3xl font-bold tracking-tight">Pricing</h1>
        <p className="mt-2 text-muted-foreground">
          Choose the plan that fits your job search
        </p>
      </div>

      <div className="mx-auto mt-12 grid max-w-5xl gap-6 md:grid-cols-3">
        {PLANS.map((plan) => {
          const cta = ctaFor(plan.tier);
          return (
            <Card
              key={plan.tier}
              className={
                plan.highlighted
                  ? "border-2 border-primary shadow-lg"
                  : "border-border"
              }
            >
              <CardHeader>
                <CardTitle className="text-xl">{TIER_LABEL[plan.tier]}</CardTitle>
                <CardDescription>{plan.tagline}</CardDescription>
                <div className="mt-3 text-3xl font-bold">{plan.price}</div>
              </CardHeader>
              <CardContent className="space-y-3">
                <ul className="space-y-2">
                  {plan.features.map((f) => {
                    const label = typeof f === "string" ? f : f.label;
                    const soon = typeof f === "object" && f.soon;
                    return (
                      <li key={label} className="flex items-start gap-2 text-sm">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                        <span>{label}</span>
                        {soon && (
                          <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide leading-none text-red-600 dark:text-red-400">
                            soon
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </CardContent>
              <CardFooter>
                <Button
                  className="w-full"
                  onClick={cta.onClick}
                  disabled={cta.disabled}
                  variant={plan.highlighted ? "default" : "outline"}
                >
                  {cta.label}
                </Button>
              </CardFooter>
            </Card>
          );
        })}
      </div>

      <Dialog
        open={!!pendingUpgrade}
        onOpenChange={(open) => !open && setPendingUpgrade(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Upgrade to {pendingUpgrade ? TIER_LABEL[pendingUpgrade] : ""}
            </DialogTitle>
            <DialogDescription>
              You'll be charged only for the remaining days of the current billing period.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            {preview.isLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Calculating amount...
              </div>
            )}
            {preview.error && (
              <p className="text-sm text-destructive">
                Failed to load preview. You can still proceed.
              </p>
            )}
            {preview.data && (
              <div className="rounded-lg border border-border bg-muted/50 p-4">
                <p className="text-sm text-muted-foreground">Due today</p>
                <p className="mt-1 text-2xl font-bold">
                  {formatAmount(preview.data.amount_due, preview.data.currency)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Prorated for remaining days in billing cycle
                </p>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setPendingUpgrade(null)}
              disabled={upgrade.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpgradeConfirm}
              disabled={upgrade.isPending || preview.isLoading}
            >
              {upgrade.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Upgrading...
                </>
              ) : (
                "Confirm upgrade"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/components/PricingContent.tsx
git commit -m "refactor(pricing): extract PricingContent component"
```

---

## Task 2: Simplify pricing/page.tsx

**Files:**
- Modify: `frontend/src/app/pricing/page.tsx`

Replace the entire file content. The `track("pricing_viewed")` call moves here so the full-page route still tracks views.

**Step 1: Replace the file**

```tsx
"use client";

import { useEffect } from "react";
import { useAnalytics } from "@/hooks/useAnalytics";
import { PricingContent } from "@/components/PricingContent";

export default function PricingPage() {
  const { track } = useAnalytics();

  useEffect(() => {
    track("pricing_viewed");
  }, [track]);

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        <PricingContent />
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 3: Commit**

```bash
git add frontend/src/app/pricing/page.tsx
git commit -m "refactor(pricing): pricing/page.tsx delegates to PricingContent"
```

---

## Task 3: Create PricingModalContext

**Files:**
- Create: `frontend/src/context/PricingModalContext.tsx`

**Step 1: Create the file**

```tsx
"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { PricingModal } from "@/components/PricingModal";

type PricingModalContextValue = {
  open: () => void;
};

const PricingModalContext = createContext<PricingModalContextValue | null>(null);

export function PricingModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <PricingModalContext.Provider value={{ open: () => setIsOpen(true) }}>
      {children}
      <PricingModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </PricingModalContext.Provider>
  );
}

export function usePricingModal(): PricingModalContextValue {
  const ctx = useContext(PricingModalContext);
  if (!ctx) throw new Error("usePricingModal must be used inside PricingModalProvider");
  return ctx;
}
```

**Step 2: Commit (PricingModal doesn't exist yet — TS will complain, commit after Task 4)**

---

## Task 4: Create PricingModal component

**Files:**
- Create: `frontend/src/components/PricingModal.tsx`

**Step 1: Create the file**

```tsx
"use client";

import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { PricingContent } from "@/components/PricingContent";

type Props = {
  isOpen: boolean;
  onClose: () => void;
};

export function PricingModal({ isOpen, onClose }: Props) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <PricingContent onClose={onClose} />
      </DialogContent>
    </Dialog>
  );
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 3: Commit both context and modal together**

```bash
git add frontend/src/context/PricingModalContext.tsx frontend/src/components/PricingModal.tsx
git commit -m "feat(pricing): add PricingModal and PricingModalContext"
```

---

## Task 5: Wire PricingModalProvider into protected layout

**Files:**
- Modify: `frontend/src/app/(protected)/layout.tsx`

**Step 1: Add import at top of file**

```tsx
import { PricingModalProvider } from "@/context/PricingModalContext";
```

**Step 2: Wrap the returned JSX**

Find the `return (` in the authenticated branch and wrap the outer `<div>` with `<PricingModalProvider>`:

```tsx
return (
  <PricingModalProvider>
    <div className="min-h-screen bg-background">
      <Navbar />
      <motion.main
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8"
      >
        {children}
      </motion.main>
    </div>
  </PricingModalProvider>
);
```

**Step 3: Verify TypeScript compiles**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 4: Commit**

```bash
git add frontend/src/app/(protected)/layout.tsx
git commit -m "feat(pricing): wire PricingModalProvider into protected layout"
```

---

## Task 6: Update entry points

**Files:**
- Modify: `frontend/src/components/QuotaBanner.tsx`
- Modify: `frontend/src/app/(protected)/optimize/page.tsx`
- Modify: `frontend/src/app/(protected)/settings/page.tsx`

### QuotaBanner.tsx

**Step 1: Add import**

```tsx
import { usePricingModal } from "@/context/PricingModalContext";
```

**Step 2: Add hook call inside `QuotaBanner` function**

```tsx
const { open } = usePricingModal();
```

**Step 3: Replace both `<Link href="/pricing">` with `<button>`**

```tsx
// BEFORE:
<Link href="/pricing" className="ml-auto underline underline-offset-4">
  Upgrade for unlimited →
</Link>

// AFTER:
<button onClick={open} className="ml-auto underline underline-offset-4">
  Upgrade for unlimited →
</button>
```

```tsx
// BEFORE:
<Link href="/pricing" className="ml-auto underline underline-offset-4">
  Upgrade →
</Link>

// AFTER:
<button onClick={open} className="ml-auto underline underline-offset-4">
  Upgrade →
</button>
```

**Step 4: Remove the `Link` import if it's no longer used**

Check if `Link` is used elsewhere in the file. If not:
```tsx
// Remove:
import Link from "next/link";
```

---

### optimize/page.tsx

**Step 1: Add import**

```tsx
import { usePricingModal } from "@/context/PricingModalContext";
```

**Step 2: Add hook call inside the component**

```tsx
const { open } = usePricingModal();
```

**Step 3: Replace `router.push("/pricing")` (line ~108)**

```tsx
// BEFORE:
router.push("/pricing");

// AFTER:
open();
```

---

### settings/page.tsx

**Step 1: Add import**

```tsx
import { usePricingModal } from "@/context/PricingModalContext";
```

**Step 2: Add hook call inside the component**

```tsx
const { open } = usePricingModal();
```

**Step 3: Replace both `<Link href="/pricing">` (lines ~121 and ~132)**

```tsx
// BEFORE (line ~121):
<Link
  href="/pricing"
  className={cn(buttonVariants(), "w-full sm:w-auto")}
>
  Upgrade
</Link>

// AFTER:
<Button onClick={open} className="w-full sm:w-auto">
  Upgrade
</Button>
```

```tsx
// BEFORE (line ~132):
<Link
  href="/pricing"
  className={cn(buttonVariants(), "w-full sm:w-auto")}
>
  Upgrade plan
</Link>

// AFTER:
<Button onClick={open} className="w-full sm:w-auto">
  Upgrade plan
</Button>
```

**Step 4: Remove `Link` import from settings/page.tsx if no longer used elsewhere in the file**

---

**Step 5: Verify TypeScript compiles**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 6: Commit**

```bash
git add frontend/src/components/QuotaBanner.tsx
git add frontend/src/app/(protected)/optimize/page.tsx
git add frontend/src/app/(protected)/settings/page.tsx
git commit -m "feat(pricing): open pricing as modal from all in-app entry points"
```

---

## Completion Check

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit && echo "TypeScript OK"
```

Manual smoke test:
1. Go to `/optimize` — trigger the quota limit (or check QuotaBanner) — pricing modal opens, no navigation away
2. Go to `/settings` — click "Upgrade" / "Upgrade plan" — modal opens
3. Navigate directly to `/pricing` — full page renders correctly (unchanged)
4. Open modal, click "×" or press Escape — closes cleanly
