-- 017_coach_trial_counter.sql — lifetime thread counter for the Coach free trial.
-- Source of truth for the "3 dialogs ever" cap on free / job_hunter tiers.
-- Counts threads ever created (not currently present) so deletes don't refund slots.
-- Idempotent: safe to re-run.

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS coach_threads_created_total INT NOT NULL DEFAULT 0;
