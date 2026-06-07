"use client";

import { useSubscription } from "@/hooks/useSubscription";

/**
 * Coach trial/lock state derived from the subscription.
 *
 * Free coach trials are locked to a single company; `isPositionLocked` reports
 * whether a given position's company differs from the locked one.
 */
export function useCoachTrialStatus() {
  const { data: sub } = useSubscription();
  const isTrialUser = sub?.coach != null && !sub.coach.is_unlimited;
  const lockedCompany = sub?.coach?.locked_company ?? null;

  const isPositionLocked = (company: string | null | undefined) =>
    isTrialUser &&
    !!lockedCompany &&
    (company ?? "").toLowerCase().trim() !== lockedCompany.toLowerCase().trim();

  return { isTrialUser, lockedCompany, isPositionLocked };
}
