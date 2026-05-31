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

  // Don't render for paid/unlimited users or while loading
  if (!sub || sub.tier !== "free" || sub.is_unlimited) return null;

  const remaining = sub.remaining ?? 0;
  if (remaining > 1) return null;

  const days = daysUntil(sub.weekly_reset_at);

  if (remaining === 1) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-900 dark:text-amber-200">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>Last optimization this week.</span>
        <button onClick={() => open()} className="ml-auto underline underline-offset-4">
          Upgrade for unlimited →
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-900 dark:text-red-200">
      <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
      <span>
        Used 3/3 this week. Resets in {days ?? "?"} day{days === 1 ? "" : "s"}.
      </span>
      <button onClick={() => open()} className="ml-auto underline underline-offset-4">
        Upgrade →
      </button>
    </div>
  );
}
