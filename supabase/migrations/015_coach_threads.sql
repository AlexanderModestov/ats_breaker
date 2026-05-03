-- 015_coach_threads.sql — multi-thread support for Coach.

-- Allow multiple threads per (user, optimization_run).
ALTER TABLE coach_sessions
    DROP CONSTRAINT IF EXISTS coach_sessions_user_id_optimization_run_id_key;

-- Optional manual title; NULL = frontend uses preview fallback.
ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS title VARCHAR(255);

-- Activity timestamp used for sidebar sort and "last active thread".
ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ;

-- Backfill so existing rows sort correctly in the new sidebar.
UPDATE coach_sessions
   SET last_message_at = updated_at
 WHERE last_message_at IS NULL;

-- Composite index for sidebar grouping query.
CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_run
    ON coach_sessions(user_id, optimization_run_id, last_message_at DESC);
