-- Add subscription columns to profiles table
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'trial'
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired')),
ADD COLUMN IF NOT EXISTS subscription_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS period_request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS addon_credits INTEGER NOT NULL DEFAULT 0;

-- Create index for subscription status queries
CREATE INDEX IF NOT EXISTS idx_profiles_subscription_status ON profiles(subscription_status);
