"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  getSubscriptionStatus,
  createCheckout,
  createBillingPortal,
} from "@/lib/api";
import type { Tier } from "@/lib/tiers";

export function useSubscription(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
    staleTime: 30_000,
    refetchInterval: options?.refetchInterval,
  });
}

export function useCheckout() {
  return useMutation({
    mutationFn: async (tier: Exclude<Tier, "free">) => {
      const baseUrl = window.location.origin;
      return createCheckout(
        tier,
        `${baseUrl}/dashboard?upgraded=${tier}`,
        `${baseUrl}/pricing`,
      );
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });
}

export function useBillingPortal() {
  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      return createBillingPortal(`${baseUrl}/dashboard`);
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });
}
