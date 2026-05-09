-- 016_user_feedback.sql — user-submitted refund/bug/idea forms.

CREATE TYPE feedback_type AS ENUM ('refund', 'bug', 'idea');

CREATE TABLE public.user_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type        feedback_type NOT NULL,
    message     text NOT NULL CHECK (char_length(message) BETWEEN 10 AND 4000),
    -- Snapshot at submission time: tier, status, current_period_end,
    -- stripe_customer_id, user_email. Captured server-side, not from client.
    context     jsonb NOT NULL DEFAULT '{}'::jsonb,
    email_sent_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_feedback_user_id_created_idx
    ON public.user_feedback (user_id, created_at DESC);

ALTER TABLE public.user_feedback ENABLE ROW LEVEL SECURITY;

-- Users can insert their own feedback only. No SELECT policy: backend uses
-- service-role client, and there is no user-facing list in the MVP.
CREATE POLICY "feedback_insert_own"
    ON public.user_feedback
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);
