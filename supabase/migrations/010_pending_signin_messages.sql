-- Tracks the "Sign in" messages the bot has sent, so the backend can edit them
-- immediately after a user completes the Telegram link flow.
CREATE TABLE IF NOT EXISTS pending_signin_messages (
    telegram_id BIGINT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
