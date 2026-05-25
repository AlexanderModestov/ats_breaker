"use client";

import { useSubscription } from "@/hooks/useSubscription";
import { usePricingModal } from "@/context/PricingModalContext";

export function QuotaBanner() {
  const { data: sub } = useSubscription();
  const { open } = usePricingModal();

  if (!sub || sub.tier !== "free" || sub.is_unlimited) return null;

  const remaining = sub.remaining ?? 0;
  if (remaining > 1) return null;

  return (
    <div className="rounded-md bg-zinc-100 px-4 py-2 text-sm text-zinc-600">
      {remaining} optimization{remaining !== 1 ? "s" : ""} left this week.{" "}
      <button
        onClick={open}
        className="font-medium text-violet-600 transition-colors hover:text-violet-700"
      >
        Upgrade →
      </button>
    </div>
  );
}
