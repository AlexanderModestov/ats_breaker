"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSubscriptionStatus,
  createSubscriptionCheckout,
  createAddonCheckout,
} from "@/lib/api";

export function useSubscription() {
  return useQuery({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
    staleTime: 30000, // 30 seconds
  });
}

export function useSubscriptionCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      const response = await createSubscriptionCheckout(
        `${baseUrl}/optimize?success=subscription`,
        `${baseUrl}/pricing`
      );
      return response;
    },
    onSuccess: (data) => {
      // Redirect to Stripe checkout
      window.location.href = data.checkout_url;
    },
  });
}

export function useAddonCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const baseUrl = window.location.origin;
      const response = await createAddonCheckout(
        `${baseUrl}/optimize?success=addon`,
        `${baseUrl}/blocked`
      );
      return response;
    },
    onSuccess: (data) => {
      // Redirect to Stripe checkout
      window.location.href = data.checkout_url;
    },
  });
}
