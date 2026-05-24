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
