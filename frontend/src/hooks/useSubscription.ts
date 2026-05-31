"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getSubscriptionStatus,
  createCheckout,
  createBillingPortal,
  previewUpgrade,
  upgradeSubscription,
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
        `${baseUrl}/optimize?upgraded=${tier}&session_id={CHECKOUT_SESSION_ID}`,
      );
    },
  });
}

export function useBillingPortal() {
  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      return createBillingPortal(`${baseUrl}/optimize`);
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });
}

export function useUpgradePreview(tier: Tier | null) {
  return useQuery({
    queryKey: ["upgrade-preview", tier],
    queryFn: () => previewUpgrade(tier!),
    enabled: !!tier,
    staleTime: 60_000,
  });
}

export function useUpgrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tier: Exclude<Tier, "free">) => upgradeSubscription(tier),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscription"] });
    },
  });
}
