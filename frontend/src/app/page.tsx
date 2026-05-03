"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { LangProvider } from "./_lib/LangContext";
import { LandingHeader } from "./_components/LandingHeader";
import { HeroSection } from "./_components/HeroSection";
import { ApplicationToOfferSection } from "./_components/ApplicationToOfferSection";
import { HowItWorksSection } from "./_components/HowItWorksSection";
import { FeaturesSection } from "./_components/FeaturesSection";
import { PricingSection } from "./_components/PricingSection";
import { FAQSection } from "./_components/FAQSection";
import { LandingFooter } from "./_components/LandingFooter";

export default function LandingPage() {
  const router = useRouter();
  const { isAuthenticated, loading } = useAuth();

  // Detect auth callback (Supabase puts token in URL hash)
  const hasAuthHash =
    typeof window !== "undefined" && window.location.hash.includes("access_token");

  useEffect(() => {
    if (!loading && isAuthenticated) {
      router.replace("/optimize");
    }
  }, [isAuthenticated, loading, router]);

  // Hide landing while processing OAuth callback or already authenticated
  if (hasAuthHash || isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  return (
    <LangProvider>
      <div className="min-h-screen bg-background">
        <LandingHeader />
        <main>
          <HeroSection />
          <ApplicationToOfferSection />
          <HowItWorksSection />
          <FeaturesSection />
          <PricingSection />
          <FAQSection />
        </main>
        <LandingFooter />
      </div>
    </LangProvider>
  );
}
