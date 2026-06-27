-- 018_metered_tiers.sql — per-tier metered limits for optimizations + coach.
-- See docs/plans/2026-06-14-metered-tiers-design.md
-- Idempotent where practical.

-- 1. Repurpose the (never-wired) lifetime coach counter as the period coach-chat counter.
ALTER TABLE profiles RENAME COLUMN coach_threads_created_total TO coach_chats_used;

-- 2. Drop the lazy weekly-window column; reset is billing-driven now.
ALTER TABLE profiles DROP COLUMN IF EXISTS weekly_reset_at;

-- 3. Remove the dead increment RPC tied to the old column name.
DROP FUNCTION IF EXISTS increment_coach_threads_created_total(UUID);

-- 4. Atomic "consume one optimization if under limit". Returns TRUE on success.
CREATE OR REPLACE FUNCTION consume_optimization_quota(p_user_id UUID, p_limit INT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE rows_affected INT;
BEGIN
    UPDATE profiles
       SET period_request_count = period_request_count + 1
     WHERE id = p_user_id
       AND period_request_count < p_limit;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 5. Atomic "consume one coach chat if under limit". Returns TRUE on success.
CREATE OR REPLACE FUNCTION consume_coach_chat_quota(p_user_id UUID, p_limit INT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE rows_affected INT;
BEGIN
    UPDATE profiles
       SET coach_chats_used = coach_chats_used + 1
     WHERE id = p_user_id
       AND coach_chats_used < p_limit;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION consume_optimization_quota(UUID, INT) TO service_role;
GRANT EXECUTE ON FUNCTION consume_coach_chat_quota(UUID, INT) TO service_role;
