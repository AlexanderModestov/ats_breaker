"use client";

import { createContext, useContext, useState, ReactNode } from "react";
import { PricingModal } from "@/components/PricingModal";

type PricingModalContextValue = {
  open: () => void;
};

const PricingModalContext = createContext<PricingModalContextValue | null>(null);

export function PricingModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <PricingModalContext.Provider value={{ open: () => setIsOpen(true) }}>
      {children}
      <PricingModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </PricingModalContext.Provider>
  );
}

export function usePricingModal(): PricingModalContextValue {
  const ctx = useContext(PricingModalContext);
  if (!ctx) throw new Error("usePricingModal must be used inside PricingModalProvider");
  return ctx;
}
