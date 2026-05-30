"use client";

import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { PricingContent } from "@/components/PricingContent";

import type { Tier } from "@/lib/tiers";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  upgradeOnly?: boolean;
  minTier?: Tier;
};

export function PricingModal({ isOpen, onClose, upgradeOnly, minTier }: Props) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className={`${upgradeOnly ? "max-w-2xl" : "max-w-5xl"} max-h-[90vh] overflow-y-auto`} onClose={onClose}>
        <PricingContent onClose={onClose} upgradeOnly={upgradeOnly} minTier={minTier} />
      </DialogContent>
    </Dialog>
  );
}
