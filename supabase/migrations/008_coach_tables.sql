-- Coach tables for AI interview coach feature

-- Coach sessions: links a user + optimization run to a coaching conversation
CREATE TABLE IF NOT EXISTS coach_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    optimization_run_id UUID NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, optimization_run_id)
);

CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_id ON coach_sessions(user_id);

-- Coach messages: stores conversation history per session
CREATE TABLE IF NOT EXISTS coach_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL UNIQUE REFERENCES coach_sessions(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_session_id ON coach_messages(session_id);

-- Storybank entries: STAR-format stories for interview preparation
CREATE TABLE IF NOT EXISTS storybank_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    situation TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT '{}',
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_storybank_entries_user_id ON storybank_entries(user_id);

-- Enable RLS on all coach tables
ALTER TABLE coach_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE storybank_entries ENABLE ROW LEVEL SECURITY;

-- Coach sessions policies
CREATE POLICY "Users can view own coach sessions"
    ON coach_sessions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own coach sessions"
    ON coach_sessions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own coach sessions"
    ON coach_sessions FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own coach sessions"
    ON coach_sessions FOR DELETE
    USING (auth.uid() = user_id);

-- Coach messages policies (access via session ownership)
CREATE POLICY "Users can view own coach messages"
    ON coach_messages FOR SELECT
    USING (session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid()));

CREATE POLICY "Users can insert own coach messages"
    ON coach_messages FOR INSERT
    WITH CHECK (session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid()));

CREATE POLICY "Users can update own coach messages"
    ON coach_messages FOR UPDATE
    USING (session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid()))
    WITH CHECK (session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid()));

CREATE POLICY "Users can delete own coach messages"
    ON coach_messages FOR DELETE
    USING (session_id IN (SELECT id FROM coach_sessions WHERE user_id = auth.uid()));

-- Storybank entries policies
CREATE POLICY "Users can view own storybank entries"
    ON storybank_entries FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own storybank entries"
    ON storybank_entries FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own storybank entries"
    ON storybank_entries FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own storybank entries"
    ON storybank_entries FOR DELETE
    USING (auth.uid() = user_id);

-- Grant service role full access (bypasses RLS)
GRANT ALL ON coach_sessions TO service_role;
GRANT ALL ON coach_messages TO service_role;
GRANT ALL ON storybank_entries TO service_role;
