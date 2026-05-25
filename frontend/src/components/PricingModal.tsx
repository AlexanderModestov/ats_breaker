"use client";

import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { PricingContent } from "@/components/PricingContent";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  upgradeOnly?: boolean;
};

export function PricingModal({ isOpen, onClose, upgradeOnly }: Props) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto" onClose={onClose}>
        <PricingContent onClose={onClose} upgradeOnly={upgradeOnly} />
      </DialogContent>
    </Dialog>
  );
}
