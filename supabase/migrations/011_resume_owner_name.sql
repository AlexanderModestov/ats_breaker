-- Persist resume owner name extracted during optimization, so the bot/UI
-- can render speaking filenames like "First Last - Company - Title.pdf".

ALTER TABLE optimization_runs
    ADD COLUMN IF NOT EXISTS first_name TEXT,
    ADD COLUMN IF NOT EXISTS last_name TEXT;

COMMENT ON COLUMN optimization_runs.first_name IS 'Resume owner first name (extracted from CV by name_extractor agent).';
COMMENT ON COLUMN optimization_runs.last_name IS 'Resume owner last name (extracted from CV by name_extractor agent).';
