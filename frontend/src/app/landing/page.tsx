"use client";

import { LangProvider } from "./_lib/LangContext";
import { LandingHeader } from "./_components/LandingHeader";
import { HeroSection } from "./_components/HeroSection";
import { HowItWorksSection } from "./_components/HowItWorksSection";
import { FeaturesSection } from "./_components/FeaturesSection";
import { PricingSection } from "./_components/PricingSection";
import { FAQSection } from "./_components/FAQSection";
import { LandingFooter } from "./_components/LandingFooter";

export default function LandingPage() {
  return (
    <LangProvider>
      <div className="min-h-screen bg-background">
        <LandingHeader />
        <main>
          <HeroSection />
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
