"use client";

import { ReactNode } from "react";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSubscription, useCheckout } from "@/hooks/useSubscription";
import {
  hasAccess,
  TIER_LABEL,
  FEATURE_MIN_TIER,
  type Feature,
  type Tier,
} from "@/lib/tiers";

const TIER_PRICE: Record<Exclude<Tier, "free">, string> = {
  job_hunter: "€19/month",
  offer_mode: "€29/month",
};

type Props = {
  feature: Feature;
  children: ReactNode;
};

export function UpgradeOverlay({ feature, children }: Props) {
  const { data: sub, isLoading } = useSubscription();
  const checkout = useCheckout();

  // While loading subscription, render children to avoid flicker
  if (isLoading) return <>{children}</>;

  const tier = sub?.tier ?? "free";
  if (hasAccess(tier, feature)) return <>{children}</>;

  const required = FEATURE_MIN_TIER[feature] as Exclude<Tier, "free">;

  return (
    <div className="relative h-full">
      <div
        aria-hidden
        className="pointer-events-none select-none blur-sm opacity-60 h-full"
      >
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="max-w-sm rounded-2xl border border-border bg-card p-6 shadow-lg text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Lock className="h-5 w-5 text-primary" />
          </div>
          <h3 className="text-lg font-semibold">
            Available in {TIER_LABEL[required]}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Upgrade to {TIER_LABEL[required]} to unlock this feature.
          </p>
          <p className="mt-3 text-2xl font-bold">{TIER_PRICE[required]}</p>
          <Button
            className="mt-4 w-full"
            onClick={() => checkout.mutate(required)}
            disabled={checkout.isPending}
          >
            {checkout.isPending ? "Loading..." : `Upgrade to ${TIER_LABEL[required]}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
