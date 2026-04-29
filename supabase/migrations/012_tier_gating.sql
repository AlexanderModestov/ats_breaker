-- Tier gating: replace single-tier paywall with three-tier model
-- Free / Job Hunter / Offer Mode. See docs/plans/2026-04-29-tier-gating-design.md

-- New columns
ALTER TABLE profiles
  ADD COLUMN subscription_tier text NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free', 'job_hunter', 'offer_mode')),
  ADD COLUMN weekly_reset_at timestamptz NOT NULL DEFAULT (now() + interval '7 days');

-- Normalize legacy status values to the new state machine (none / active / cancelled)
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'trial';
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'expired';

-- Drop deprecated columns from the addon-era model
ALTER TABLE profiles
  DROP COLUMN IF EXISTS request_count,
  DROP COLUMN IF EXISTS addon_credits;
