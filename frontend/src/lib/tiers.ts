export type Tier = "free" | "job_hunter" | "offer_mode";

export const TIER_RANK: Record<Tier, number> = {
  free: 0,
  job_hunter: 1,
  offer_mode: 2,
};

export const FEATURE_MIN_TIER = {
  optimize: "free",
  coach: "free",
  cover_letter: "offer_mode",
  gap_analysis: "offer_mode",
} as const satisfies Record<string, Tier>;

export type Feature = keyof typeof FEATURE_MIN_TIER;

export function hasAccess(currentTier: Tier, feature: Feature): boolean {
  return TIER_RANK[currentTier] >= TIER_RANK[FEATURE_MIN_TIER[feature]];
}

export const TIER_LABEL: Record<Tier, string> = {
  free: "Starter",
  job_hunter: "Job Hunter",
  offer_mode: "Offer Mode",
};

export const TIER_LIMITS: Record<Tier, { optimizations: number; coachChats: number; coachMsgs: number }> = {
  free:       { optimizations: 3,  coachChats: 1,  coachMsgs: 15 },
  job_hunter: { optimizations: 20, coachChats: 1,  coachMsgs: 15 },
  offer_mode: { optimizations: 40, coachChats: 10, coachMsgs: 20 },
};
