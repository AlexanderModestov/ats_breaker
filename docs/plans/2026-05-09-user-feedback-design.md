# User Feedback / Refund Request — Design

**Date:** 2026-05-09
**Status:** Design approved, ready for implementation plan

## Goal

Give users a transparent way to send refund requests, bug reports, and ideas/comments to the team. Today there is no in-app channel for this; users have no clear path other than direct email guesswork.

## Scope (MVP)

- Three submission types: `refund`, `bug`, `idea`.
- Single entry point: a new "Support / Feedback" card on `/settings`.
- Backend persists each submission in Supabase **and** sends an email notification to the team via Resend.
- User feedback after submit: a toast "Message sent". No history list, no status tracking in the UI (deferred for later).
- Refunds are processed manually by the team via Stripe Dashboard. No automatic Stripe refund API calls.

## Out of scope (YAGNI)

- Attachments / screenshots.
- Automatic Stripe refund.
- User-facing list/status of past submissions.
- Admin dashboard (Supabase Studio is enough).
- Email templating engine — plain f-string is sufficient for one template.
- Background queue / retry logic — synchronous Resend send is fine at this volume.

## Architecture

```
User → /settings (SupportCard)
  → POST /api/feedback {type, message}
    → INSERT into public.user_feedback (Supabase)
    → Resend.send(...) → SUPPORT_EMAIL_TO
  → 200 OK → toast "Message sent"
```

## Data model

New migration: `supabase/migrations/016_user_feedback.sql`

```sql
create type feedback_type as enum ('refund', 'bug', 'idea');

create table public.user_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type feedback_type not null,
  message text not null check (char_length(message) between 10 and 4000),
  context jsonb not null default '{}'::jsonb,
  -- snapshot at submission time:
  -- {tier, status, current_period_end, stripe_customer_id, user_email}
  email_sent_at timestamptz,
  created_at timestamptz not null default now()
);

create index user_feedback_user_id_idx on public.user_feedback(user_id);

alter table public.user_feedback enable row level security;

create policy "feedback_insert_own" on public.user_feedback
  for insert with check (auth.uid() = user_id);
-- No SELECT policy: only service role reads via Supabase Studio.
```

The `context` jsonb is captured server-side from the user's profile, not from the client. This guarantees the team has accurate billing context for refund requests even if the client UI is stale.

## API

New route: `src/hr_breaker/api/routes/feedback.py` → `POST /api/feedback`

Request:
```json
{
  "type": "refund" | "bug" | "idea",
  "message": "string, 10–4000 chars"
}
```

Response: `200 {"ok": true}` | `422` validation | `429` rate limit | `401` unauth.

Server flow:
1. Pydantic validation (`type` enum, `message` length 10–4000, strip whitespace).
2. **Rate limit:** count user's submissions in last 1 hour; if `>= 5` → `429`.
3. Build `context` snapshot from the user's profile (tier, status, current_period_end, stripe_customer_id, user_email).
4. INSERT row → get `feedback_id`.
5. Try `email_service.send_feedback_notification(...)`:
   - Success → UPDATE `email_sent_at = now()`.
   - Failure → log error, **do not** rollback INSERT, still return 200.
6. Return `{ok: true}`.

The email-failure-still-persists choice is deliberate: a saved row that the team can find via `WHERE email_sent_at IS NULL` is better than losing the user's submission to a transient Resend outage.

## Email integration (Resend)

Dependencies:
- `resend>=2.0` in `pyproject.toml`.
- ENV: `RESEND_API_KEY`, `SUPPORT_EMAIL_TO`, `SUPPORT_EMAIL_FROM` (must be on a Resend-verified domain).

New service: `src/hr_breaker/services/email_service.py`

```python
class EmailService:
    def __init__(self):
        resend.api_key = settings.RESEND_API_KEY

    def send_feedback_notification(
        self,
        *,
        feedback_id: str,
        feedback_type: Literal["refund", "bug", "idea"],
        user_email: str | None,
        message: str,
        context: dict,
    ) -> None:
        subject = f"[{feedback_type.upper()}] from {user_email or 'unknown'}"
        html = render_feedback_email(...)  # simple f-string, html.escape() on user input
        resend.Emails.send({
            "from": settings.SUPPORT_EMAIL_FROM,
            "to": [settings.SUPPORT_EMAIL_TO],
            "reply_to": user_email,  # team replies go straight to user
            "subject": subject,
            "html": html,
        })
```

Email body (plain HTML, no Jinja):

```
Type: refund
User: user@example.com (id: 8f3a...)
Submitted: 2026-05-09 14:23 UTC
Feedback ID: 9c2b...

Subscription context:
  Tier: job_hunter
  Status: active
  Period end: 2026-06-01
  Stripe customer: cus_xxx

Message:
─────────────────────────────────
{html-escaped user message}
─────────────────────────────────

Reply directly to this email — it goes to the user.
```

`reply_to: user_email` is the key UX choice: the team's reply lands directly in the user's inbox, no need to copy-paste addresses.

## Frontend

Page: `frontend/src/app/(protected)/settings/page.tsx` — add a new `<SupportCard />` next to the existing `<SubscriptionCard />`.

New component: `frontend/src/app/(protected)/settings/_components/SupportCard.tsx` (uses existing shadcn `Card`, `Tabs`, `Textarea`, `Button` — same style as the rest of the page).

Layout:

```
┌─ Support / Feedback ─────────────────┐
│ Need help? Send us a message.        │
│                                       │
│ Type: [ Refund | Bug | Idea ]        │  ← Tabs
│                                       │
│ (refund only) You're on Job Hunter,  │
│ renews 2026-06-01.                   │
│                                       │
│ ┌──────────────────────────────────┐ │
│ │ Your message...                  │ │  ← Textarea, 10–4000
│ │                                  │ │
│ └──────────────────────────────────┘ │
│ 0/4000                       [Send] │
└──────────────────────────────────────┘
```

Type-specific placeholders:
- `Refund` — "Reason for refund + which payment".
- `Bug` — "What happened? Steps to reproduce".
- `Idea` — "What would make HR-Breaker better for you?".

UI states:
- `idle` → form active.
- `pending` → button disabled, spinner.
- `success` → form cleared, toast "Thanks! We'll reach out via email"; submit disabled for 30s to prevent double-send.
- `error` → inline red message, retry possible, form not cleared.

Tech:
- `useMutation` from react-query.
- `submitFeedback(body)` added to `frontend/src/lib/api.ts`.
- `FeedbackType = 'refund' | 'bug' | 'idea'` in `frontend/src/types/index.ts`.
- Toast via whatever toast system the app already uses.

Client validation mirrors server: 10–4000 chars, button disabled until valid. No preview/confirm modal.

## Edge cases

| Case | Behavior |
|------|----------|
| User without email (Telegram-only signup) | Allowed; `reply_to` omitted; email body says "no email on file". |
| User without subscription (free tier) | Refund type still allowed; `context.tier = free`. |
| Resend down / SDK throws | INSERT persists, `email_sent_at` stays NULL, user sees success. |
| Double-click / double-submit | Frontend disables submit for 30s after success + server rate limit. |
| XSS in message rendered in email HTML | `html.escape()` on user input before f-string. |
| Message over 4000 chars | Pydantic `max_length` rejects with 422; client counter prevents most cases. |

## Testing

`tests/api/test_feedback.py` (Resend SDK mocked):

- `test_submit_feedback_creates_row_and_sends_email`
- `test_submit_feedback_too_short_returns_422`
- `test_submit_feedback_too_long_returns_422`
- `test_submit_feedback_unauthenticated_returns_401`
- `test_rate_limit_after_5_requests_returns_429`
- `test_email_failure_still_persists_and_returns_200`
- `test_context_snapshot_includes_tier_and_period_end`
- `test_html_special_chars_escaped_in_email`

No E2E / Playwright — form is simple enough that API unit tests + manual smoke cover it.

## File list

**Backend:**
1. `src/hr_breaker/services/email_service.py` (new)
2. `src/hr_breaker/api/routes/feedback.py` (new)
3. `src/hr_breaker/api/main.py` (register router)
4. `src/hr_breaker/config.py` (3 new env vars)
5. `pyproject.toml` (add `resend>=2.0`)

**DB:**
6. `supabase/migrations/016_user_feedback.sql` (new)

**Frontend:**
7. `frontend/src/app/(protected)/settings/page.tsx` (add SupportCard)
8. `frontend/src/app/(protected)/settings/_components/SupportCard.tsx` (new)
9. `frontend/src/lib/api.ts` (add `submitFeedback`)
10. `frontend/src/types/index.ts` (add types)

**Tests:**
11. `tests/api/test_feedback.py` (new, 8 cases)

**Env:**
12. `.env.example` (3 new vars)

## Open questions / future work

- History UI with status (open / in_progress / resolved) — deferred until volume justifies it.
- Auto-refund within N days of payment — needs an explicit refund policy first.
- Telegram fallback notification if Resend fails — not needed unless deliverability becomes an issue.
