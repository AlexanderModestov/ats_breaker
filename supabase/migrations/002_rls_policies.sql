-- Row-Level Security (RLS) policies for HR-Breaker
-- Ensures users can only access their own data

-- Enable RLS on all tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cvs ENABLE ROW LEVEL SECURITY;
ALTER TABLE optimization_runs ENABLE ROW LEVEL SECURITY;

-- Profiles policies
-- Users can view their own profile
CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT
    USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Allow insert during signup (profile trigger)
CREATE POLICY "Enable insert for authenticated users only"
    ON profiles FOR INSERT
    WITH CHECK (auth.uid() = id);

-- CVs policies
-- Users can view their own CVs
CREATE POLICY "Users can view own CVs"
    ON cvs FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own CVs
CREATE POLICY "Users can insert own CVs"
    ON cvs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own CVs
CREATE POLICY "Users can update own CVs"
    ON cvs FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Users can delete their own CVs
CREATE POLICY "Users can delete own CVs"
    ON cvs FOR DELETE
    USING (auth.uid() = user_id);

-- Optimization runs policies
-- Users can view their own optimization runs
CREATE POLICY "Users can view own optimization runs"
    ON optimization_runs FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own optimization runs
CREATE POLICY "Users can insert own optimization runs"
    ON optimization_runs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own optimization runs
CREATE POLICY "Users can update own optimization runs"
    ON optimization_runs FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Users can delete their own optimization runs
CREATE POLICY "Users can delete own optimization runs"
    ON optimization_runs FOR DELETE
    USING (auth.uid() = user_id);

-- Grant service role full access (bypasses RLS)
-- This is used by the backend API with service key
GRANT ALL ON profiles TO service_role;
GRANT ALL ON cvs TO service_role;
GRANT ALL ON optimization_runs TO service_role;
