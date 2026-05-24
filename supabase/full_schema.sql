-- ============================================================
-- HR-Breaker: Full schema (migrations 001–017)
-- Run this in the Supabase SQL Editor on a fresh instance.
-- ============================================================


-- ============================================================
-- 001: Initial schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT,
    theme TEXT NOT NULL DEFAULT 'minimal' CHECK (theme IN ('minimal', 'professional', 'bold')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cvs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    content_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cvs_user_id ON cvs(user_id);
CREATE INDEX IF NOT EXISTS idx_cvs_created_at ON cvs(created_at DESC);

CREATE TABLE IF NOT EXISTS optimization_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    cv_id UUID NOT NULL REFERENCES cvs(id) ON DELETE CASCADE,
    job_input TEXT NOT NULL,
    job_parsed JSONB,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'parse_job', 'generate', 'validate', 'refine', 'complete', 'failed')),
    current_step TEXT,
    iterations INTEGER NOT NULL DEFAULT 0,
    result_html TEXT,
    result_pdf_path TEXT,
    feedback JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_optimization_runs_user_id ON optimization_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_optimization_runs_cv_id ON optimization_runs(cv_id);
CREATE INDEX IF NOT EXISTS idx_optimization_runs_status ON optimization_runs(status);
CREATE INDEX IF NOT EXISTS idx_optimization_runs_created_at ON optimization_runs(created_at DESC);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cvs_updated_at
    BEFORE UPDATE ON cvs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_optimization_runs_updated_at
    BEFORE UPDATE ON optimization_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 002: RLS policies
-- ============================================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cvs ENABLE ROW LEVEL SECURITY;
ALTER TABLE optimization_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
    ON profiles FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE USING (auth.uid() = id) WITH CHECK (auth.uid() = id);

CREATE POLICY "Enable insert for authenticated users only"
    ON profiles FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can view own CVs"
    ON cvs FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own CVs"
    ON cvs FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own CVs"
    ON cvs FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own CVs"
    ON cvs FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view own optimization runs"
    ON optimization_runs FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own optimization runs"
    ON optimization_runs FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own optimization runs"
    ON optimization_runs FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own optimization runs"
    ON optimization_runs FOR DELETE USING (auth.uid() = user_id);

GRANT ALL ON profiles TO service_role;
GRANT ALL ON cvs TO service_role;
GRANT ALL ON optimization_runs TO service_role;


-- ============================================================
-- 003: Storage buckets
-- ============================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'cvs', 'cvs', false, 10485760,
    ARRAY['application/pdf', 'text/plain', 'text/x-tex', 'text/markdown', 'text/html']
) ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'results', 'results', false, 10485760,
    ARRAY['application/pdf']
) ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Users can upload CVs to own folder"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'cvs' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can view own CVs"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'cvs' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can delete own CVs"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'cvs' AND auth.uid()::text = (storage.foldername(name))[1]);

CREATE POLICY "Users can view own results"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'results' AND auth.uid()::text = (storage.foldername(name))[1]);


-- ============================================================
-- 004: Profile trigger on signup
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, name, theme)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'name', NEW.raw_user_meta_data->>'full_name'),
        'minimal'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

GRANT EXECUTE ON FUNCTION public.handle_new_user() TO service_role;


-- ============================================================
-- 005: Subscription columns
-- ============================================================

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS subscription_status TEXT NOT NULL DEFAULT 'trial'
    CHECK (subscription_status IN ('trial', 'active', 'cancelled', 'expired')),
ADD COLUMN IF NOT EXISTS subscription_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS period_request_count INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS addon_credits INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_profiles_subscription_status ON profiles(subscription_status);


-- ============================================================
-- 006: consume_request function
-- ============================================================

CREATE OR REPLACE FUNCTION consume_request(
    p_user_id UUID,
    p_is_subscriber BOOLEAN,
    p_subscription_limit INTEGER DEFAULT 50
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    rows_affected INTEGER;
BEGIN
    IF p_is_subscriber THEN
        UPDATE profiles
        SET period_request_count = period_request_count + 1
        WHERE id = p_user_id AND period_request_count < p_subscription_limit;
        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        IF rows_affected > 0 THEN RETURN TRUE; END IF;

        UPDATE profiles
        SET addon_credits = addon_credits - 1
        WHERE id = p_user_id AND addon_credits > 0;
        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        RETURN rows_affected > 0;
    ELSE
        UPDATE profiles SET request_count = request_count + 1 WHERE id = p_user_id;
        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        RETURN rows_affected > 0;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION add_addon_credits(p_user_id UUID, p_credits INTEGER)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    rows_affected INTEGER;
BEGIN
    UPDATE profiles SET addon_credits = addon_credits + p_credits WHERE id = p_user_id;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;


-- ============================================================
-- 007: Timing column
-- ============================================================

ALTER TABLE optimization_runs ADD COLUMN IF NOT EXISTS timing JSONB;


-- ============================================================
-- 008: Coach tables
-- ============================================================

CREATE TABLE IF NOT EXISTS coach_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    optimization_run_id UUID NOT NULL REFERENCES optimization_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, optimization_run_id)
);

CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_id ON coach_sessions(user_id);

CREATE TABLE IF NOT EXISTS coach_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL UNIQUE REFERENCES coach_sessions(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_session_id ON coach_messages(session_id);

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

ALTER TABLE coach_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE storybank_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own coach sessions"
    ON coach_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own coach sessions"
    ON coach_sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own coach sessions"
    ON coach_sessions FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own coach sessions"
    ON coach_sessions FOR DELETE USING (auth.uid() = user_id);

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

CREATE POLICY "Users can view own storybank entries"
    ON storybank_entries FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own storybank entries"
    ON storybank_entries FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own storybank entries"
    ON storybank_entries FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own storybank entries"
    ON storybank_entries FOR DELETE USING (auth.uid() = user_id);

GRANT ALL ON coach_sessions TO service_role;
GRANT ALL ON coach_messages TO service_role;
GRANT ALL ON storybank_entries TO service_role;


-- ============================================================
-- 009: Telegram ID
-- ============================================================

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telegram_id BIGINT UNIQUE;
CREATE INDEX IF NOT EXISTS idx_profiles_telegram_id ON profiles(telegram_id);


-- ============================================================
-- 010: Pending signin messages
-- ============================================================

CREATE TABLE IF NOT EXISTS pending_signin_messages (
    telegram_id BIGINT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- 011: Resume owner name
-- ============================================================

ALTER TABLE optimization_runs
    ADD COLUMN IF NOT EXISTS first_name TEXT,
    ADD COLUMN IF NOT EXISTS last_name TEXT;


-- ============================================================
-- 012: Tier gating
-- ============================================================

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS subscription_tier TEXT NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free', 'job_hunter', 'offer_mode')),
  ADD COLUMN IF NOT EXISTS weekly_reset_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days');

ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_subscription_status_check;

UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'trial';
UPDATE profiles SET subscription_status = 'none' WHERE subscription_status = 'expired';

ALTER TABLE profiles
  ADD CONSTRAINT profiles_subscription_status_check
    CHECK (subscription_status IN ('none', 'active', 'cancelled'));

ALTER TABLE profiles
  DROP COLUMN IF EXISTS request_count,
  DROP COLUMN IF EXISTS addon_credits;


-- ============================================================
-- 013: Default CV
-- ============================================================

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS default_cv_id UUID REFERENCES cvs(id) ON DELETE SET NULL;


-- ============================================================
-- 014: Fix subscription_status default
-- ============================================================

ALTER TABLE profiles ALTER COLUMN subscription_status SET DEFAULT 'none';


-- ============================================================
-- 015: Coach threads (multi-thread support)
-- ============================================================

ALTER TABLE coach_sessions
    DROP CONSTRAINT IF EXISTS coach_sessions_user_id_optimization_run_id_key;

ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS title VARCHAR(255);

ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ;

UPDATE coach_sessions SET last_message_at = updated_at WHERE last_message_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_run
    ON coach_sessions(user_id, optimization_run_id, last_message_at DESC);


-- ============================================================
-- 016: User feedback
-- ============================================================

CREATE TYPE feedback_type AS ENUM ('refund', 'bug', 'idea');

CREATE TABLE public.user_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type        feedback_type NOT NULL,
    message     TEXT NOT NULL CHECK (char_length(message) BETWEEN 10 AND 4000),
    context     JSONB NOT NULL DEFAULT '{}'::jsonb,
    email_sent_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX user_feedback_user_id_created_idx
    ON public.user_feedback (user_id, created_at DESC);

ALTER TABLE public.user_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "feedback_insert_own"
    ON public.user_feedback FOR INSERT WITH CHECK (auth.uid() = user_id);


-- ============================================================
-- 017: Coach trial counter
-- ============================================================

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
