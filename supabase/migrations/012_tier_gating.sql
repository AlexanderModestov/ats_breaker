-- Tier gating: replace single-tier paywall with three-tier model
-- Free / Job Hunter / Offer Mode. See docs/plans/2026-04-29-tier-gating-design.md
--
-- Migration is idempotent — safe to re-run if a partial apply happened.

-- 1. Add new columns (idempotent)
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS subscription_tier text NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free', 'job_hunter', 'offer_mode')),
  ADD COLUMN IF NOT EXISTS weekly_reset_at timestamptz NOT NULL DEFAULT (now() + interval '7 days');

-- 2. Drop the legacy subscription_status CHECK constraint so we can normalize values
--    (the constraint from migration 005 only allowed trial/active/cancelled/expired)
ALTER TABLE profiles
  DROP CONSTRAINT IF EXISTS profiles_subscription_status_check;

-- 3. Normalize legacy values to the new state machine (none / active / cancelled)
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'trial';
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'expired';

-- 4. Re-add CHECK with the new allowed values
ALTER TABLE profiles
  ADD CONSTRAINT profiles_subscription_status_check
    CHECK (subscription_status IN ('none', 'active', 'cancelled'));

-- 5. Drop deprecated columns from the addon-era model
ALTER TABLE profiles
  DROP COLUMN IF EXISTS request_count,
  DROP COLUMN IF EXISTS addon_credits;
