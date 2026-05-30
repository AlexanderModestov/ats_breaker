"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { PricingModal } from "@/components/PricingModal";
import type { Tier } from "@/lib/tiers";

type OpenOptions = { minTier?: Tier };

type PricingModalContextValue = {
  open: (options?: OpenOptions) => void;
};

const PricingModalContext = createContext<PricingModalContextValue | null>(null);

export function PricingModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [options, setOptions] = useState<OpenOptions>({});

  const open = (opts?: OpenOptions) => {
    setOptions(opts ?? {});
    setIsOpen(true);
  };

  return (
    <PricingModalContext.Provider value={{ open }}>
      {children}
      <PricingModal isOpen={isOpen} onClose={() => setIsOpen(false)} minTier={options.minTier} />
    </PricingModalContext.Provider>
  );
}

export function usePricingModal(): PricingModalContextValue {
  const ctx = useContext(PricingModalContext);
  if (!ctx) throw new Error("usePricingModal must be used inside PricingModalProvider");
  return ctx;
}
