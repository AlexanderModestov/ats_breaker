-- 017_coach_trial_counter.sql — lifetime thread counter for the Coach free trial.
-- Source of truth for the "3 dialogs ever" cap on free / job_hunter tiers.
-- Counts threads ever created (not currently present) so deletes don't refund slots.
-- Idempotent: safe to re-run.

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS coach_threads_created_total INT NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION increment_coach_threads_created_total(p_user_id UUID)
RETURNS VOID
LANGUAGE SQL
SECURITY DEFINER
AS $$
  UPDATE profiles
     SET coach_threads_created_total = coach_threads_created_total + 1
   WHERE id = p_user_id;
$$;

GRANT EXECUTE ON FUNCTION increment_coach_threads_created_total(UUID) TO service_role;
