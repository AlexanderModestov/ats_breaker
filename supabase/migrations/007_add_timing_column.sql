-- Add timing column to optimization_runs for performance tracking
ALTER TABLE optimization_runs ADD COLUMN IF NOT EXISTS timing JSONB;

COMMENT ON COLUMN optimization_runs.timing IS 'Timing breakdown in seconds: scrape_job, parse_job, extract_name, optimization_loop, total';
