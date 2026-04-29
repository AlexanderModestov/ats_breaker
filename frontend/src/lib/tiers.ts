export type Tier = "free" | "job_hunter" | "offer_mode";

export const TIER_RANK: Record<Tier, number> = {
  free: 0,
  job_hunter: 1,
  offer_mode: 2,
};

export const FEATURE_MIN_TIER = {
  optimize: "free",
  coach: "offer_mode",
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
