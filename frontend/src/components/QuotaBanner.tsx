"use client";

import { AlertCircle, AlertTriangle } from "lucide-react";
import { useSubscription } from "@/hooks/useSubscription";
import { usePricingModal } from "@/context/PricingModalContext";

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

export function QuotaBanner() {
  const { data: sub } = useSubscription();
  const { open } = usePricingModal();

  if (!sub) return null;

  const { remaining, renews_at } = sub.optimizations;
  if (remaining > 1) return null;

  const isOfferMode = sub.tier === "offer_mode";
  const days = daysUntil(renews_at);
  const resetLabel =
    days === null
      ? null
      : sub.status === "cancelled"
        ? `Access ends in ${days} day${days === 1 ? "" : "s"}.`
        : `Renews in ${days} day${days === 1 ? "" : "s"}.`;

  if (remaining === 1) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>Last optimization remaining.</span>
        {!isOfferMode && (
          <button onClick={() => open()} className="ml-auto underline underline-offset-4">
            Upgrade →
          </button>
        )}
      </div>
    );
  }

  // remaining === 0
  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-900 dark:text-red-200">
      <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
      <span>
        Limit reached.{sub.tier !== "free" && resetLabel ? ` ${resetLabel}` : ""}
      </span>
      {!isOfferMode && (
        <button onClick={() => open()} className="ml-auto underline underline-offset-4">
          Upgrade →
        </button>
      )}
    </div>
  );
}
