"use client";

import { useEffect, useRef } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!,
);

type Props = {
  clientSecret: string;
  onClose: () => void;
};

export function EmbeddedCheckoutModal({ clientSecret, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let checkout: { destroy: () => void } | null = null;

    stripePromise.then(async (stripe) => {
      if (!stripe || !containerRef.current) return;
      checkout = await stripe.initEmbeddedCheckout({ clientSecret });
      if (containerRef.current) {
        checkout.mount(containerRef.current);
      }
    });

    return () => {
      checkout?.destroy();
    };
  }, [clientSecret]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-lg rounded-xl bg-background shadow-2xl">
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-3 top-3 z-10"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
        <div ref={containerRef} className="max-h-[90vh] overflow-y-auto rounded-xl" />
      </div>
    </div>
  );
}
