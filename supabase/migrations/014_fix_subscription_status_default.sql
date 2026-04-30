-- Align subscription_status column default with the tier_gating CHECK from 012.
-- Default was 'trial' (from 005) but 012's CHECK forbids it, so the
-- handle_new_user trigger failed on first sign-in: "Database error saving new user".
ALTER TABLE profiles
  ALTER COLUMN subscription_status SET DEFAULT 'none';
