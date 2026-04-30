-- Add default CV reference to profiles for /settings and /optimize
ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS default_cv_id UUID REFERENCES cvs(id) ON DELETE SET NULL;
