"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import {
  useSubscription,
  useCheckout,
  useBillingPortal,
} from "@/hooks/useSubscription";
import { useAnalytics } from "@/hooks/useAnalytics";
import { TIER_LABEL, type Tier } from "@/lib/tiers";

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

type CtaState = {
  label: string;
  onClick: () => void;
  disabled: boolean;
};

export default function PricingPage() {
  const router = useRouter();
  const { isAuthenticated, loading: authLoading } = useAuth();
  const { data: sub } = useSubscription();
  const checkout = useCheckout();
  const portal = useBillingPortal();
  const { track } = useAnalytics();

  useEffect(() => {
    track("pricing_viewed");
  }, [track]);

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

    // planTier is job_hunter or offer_mode, and user is on a different tier
    if (current === "free") {
      return {
        label: "Subscribe",
        onClick: () =>
          checkout.mutate(planTier as Exclude<Tier, "free">),
        disabled: checkout.isPending,
      };
    }

    return {
      label: "Switch plan",
      onClick: () => portal.mutate(),
      disabled: portal.isPending,
    };
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
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
                  <CardTitle className="text-xl">
                    {TIER_LABEL[plan.tier]}
                  </CardTitle>
                  <CardDescription>{plan.tagline}</CardDescription>
                  <div className="mt-3 text-3xl font-bold">{plan.price}</div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <ul className="space-y-2">
                    {plan.features.map((f) => {
                      const label = typeof f === "string" ? f : f.label;
                      const soon = typeof f === "object" && f.soon;
                      return (
                        <li
                          key={label}
                          className="flex items-start gap-2 text-sm"
                        >
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
      </div>
    </div>
  );
}
