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
      "3 resume optimizations total",
      "Basic ATS optimization",
      "Keyword highlights",
      "AI Interview Prep — 1 chat, 15 messages",
      "PDF download",
    ],
  },
  {
    tier: "job_hunter",
    price: "€19/month",
    tagline: "Get more interviews",
    features: [
      "Everything in Starter +",
      "20 resume optimizations / month",
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
      "40 resume optimizations / month",
      "AI interview prep — 10 chats, 20 messages",
      "Answers to common questions",
      "STAR-structured responses",
      "Personalized feedback",
      "Gap analysis",
      { label: "Cover letter generator", soon: true },
    ],
  },
];

function formatAmount(amountCents: number, currency: string) {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
  }).format(amountCents / 100);
}

type CtaState = { label: string; onClick: () => void; disabled: boolean };

type Props = {
  onClose?: () => void;
  upgradeOnly?: boolean;
  minTier?: Tier;
};

export function PricingContent({ onClose, upgradeOnly, minTier }: Props) {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const { data: sub } = useSubscription();
  const checkout = useCheckout();
  const portal = useBillingPortal();
  const upgrade = useUpgrade();

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

      <div
        className={[
          "mx-auto mt-12 grid gap-6",
          (() => {
            const count = PLANS.filter(
              (plan) =>
                (!upgradeOnly || TIER_RANK[plan.tier] > TIER_RANK[sub?.tier ?? "free"]) &&
                (!minTier || TIER_RANK[plan.tier] >= TIER_RANK[minTier]),
            ).length;
            if (count === 1) return "max-w-sm grid-cols-1";
            if (count === 2) return "max-w-2xl grid-cols-2";
            return "max-w-5xl md:grid-cols-3";
          })(),
        ].join(" ")}
      >
        {PLANS.filter(
          (plan) =>
            (!upgradeOnly || TIER_RANK[plan.tier] > TIER_RANK[sub?.tier ?? "free"]) &&
            (!minTier || TIER_RANK[plan.tier] >= TIER_RANK[minTier]),
        ).map((plan) => {
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
