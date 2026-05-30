"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAnalytics } from "@/hooks/useAnalytics";
import { PricingContent } from "@/components/PricingContent";
import { TIER_LABEL } from "@/lib/tiers";
import type { Tier } from "@/lib/tiers";

function PricingPageContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { track } = useAnalytics();

  useEffect(() => {
    track("pricing_viewed");
  }, [track]);

  useEffect(() => {
    const upgraded = searchParams.get("upgraded");
    if (upgraded === "job_hunter" || upgraded === "offer_mode") {
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
      window.history.replaceState({}, "", "/pricing");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const upgraded = searchParams.get("upgraded") as Exclude<Tier, "free"> | null;
  const showSuccess = upgraded === "job_hunter" || upgraded === "offer_mode";

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-16">
        {showSuccess && (
          <div className="mx-auto mb-8 max-w-2xl">
            <Alert className="border-green-200 bg-green-50 text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-200">
              <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
              <AlertDescription>
                Welcome to {TIER_LABEL[upgraded]}! Your subscription is active.
              </AlertDescription>
            </Alert>
          </div>
        )}
        <PricingContent />
      </div>
    </div>
  );
}

export default function PricingPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <PricingPageContent />
    </Suspense>
  );
}
