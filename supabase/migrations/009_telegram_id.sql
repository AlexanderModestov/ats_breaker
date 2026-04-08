-- Add telegram_id to profiles for Telegram bot linking
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telegram_id BIGINT UNIQUE;

CREATE INDEX IF NOT EXISTS idx_profiles_telegram_id ON profiles(telegram_id);
