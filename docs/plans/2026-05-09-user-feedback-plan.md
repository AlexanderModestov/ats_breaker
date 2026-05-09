# User Feedback / Refund Request — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a user-facing feedback channel (refund / bug / idea) that persists submissions to Supabase and emails the team via Resend.

**Architecture:** New `POST /api/feedback` route persists into `public.user_feedback` and synchronously sends an email via Resend. Email failure does not block persistence (team can find unsent rows by `email_sent_at IS NULL`). Frontend adds a `<SupportCard />` to `/settings` with a 3-tab type selector and a textarea. Inline success state, no toast library.

**Tech Stack:** FastAPI + Pydantic + Supabase (Python service-role client) + Resend Python SDK on the backend; Next.js + React Query + shadcn `Card`/`Tabs`/`Button` on the frontend.

**Design doc:** `docs/plans/2026-05-09-user-feedback-design.md`

---

## Conventions

- Existing test pattern: `tests/test_<area>.py`, FastAPI `TestClient`, `app.dependency_overrides` to inject fakes (see `tests/test_coach_routes.py`).
- All commands run from repo root unless noted.
- Commit messages follow conventional commits style used in the project (e.g., `feat(feedback): ...`, `test(feedback): ...`).
- TDD: write the failing test, see it fail, write minimal code, see it pass, commit.

---

## Task 1: Add Resend dependency and config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/hr_breaker/config.py`
- Modify: `.env.example`

**Step 1: Add the dependency**

Edit `pyproject.toml` — find the `[project]` `dependencies = [...]` list and add:

```
"resend>=2.0",
```

Then run:

```bash
uv sync
```

Expected: lockfile updates, no errors.

**Step 2: Add settings fields**

In `src/hr_breaker/config.py`, in the `Settings` class (after `telegram_bot_token`), add:

```python
    # Feedback / Resend settings
    resend_api_key: str = ""
    support_email_to: str = ""
    support_email_from: str = ""
```

In `get_settings()`, in the `Settings(...)` constructor (alongside the `telegram_bot_token=...` line), add:

```python
        resend_api_key=os.getenv("RESEND_API_KEY", ""),
        support_email_to=os.getenv("SUPPORT_EMAIL_TO", ""),
        support_email_from=os.getenv("SUPPORT_EMAIL_FROM", ""),
```

**Step 3: Add to `.env.example`**

Append at end of `.env.example`:

```
# Feedback / Resend (required for /api/feedback to deliver emails)
RESEND_API_KEY=re_xxx
SUPPORT_EMAIL_TO=support@example.com
SUPPORT_EMAIL_FROM=noreply@example.com
```

**Step 4: Smoke test**

```bash
uv run python -c "from hr_breaker.config import get_settings; s = get_settings(); print(s.resend_api_key, s.support_email_to, s.support_email_from)"
```

Expected: prints three empty strings (no env set yet) without error.

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/hr_breaker/config.py .env.example
git commit -m "feat(feedback): add resend dependency and settings"
```

---

## Task 2: Database migration

**Files:**
- Create: `supabase/migrations/016_user_feedback.sql`

**Step 1: Create migration file**

```sql
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
```

**Step 2: Verify file**

```bash
ls supabase/migrations/016_user_feedback.sql
```

Expected: file exists.

(The migration runs against Supabase via the project's normal deployment flow — not executed here.)

**Step 3: Commit**

```bash
git add supabase/migrations/016_user_feedback.sql
git commit -m "feat(feedback): add user_feedback table migration"
```

---

## Task 3: Email service — failing test

**Files:**
- Create: `tests/test_email_service.py`

**Step 1: Write the failing test**

```python
"""Tests for EmailService — Resend wrapper."""

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def patched_settings():
    with patch("hr_breaker.services.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            resend_api_key="test-key",
            support_email_from="noreply@test.com",
            support_email_to="support@test.com",
        )
        yield gs


def test_send_feedback_notification_calls_resend_with_expected_payload(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-1",
            feedback_type="refund",
            user_email="alice@example.com",
            message="please refund me",
            context={"tier": "job_hunter", "status": "active"},
        )

    assert fake_resend.api_key == "test-key"
    fake_resend.Emails.send.assert_called_once()
    payload = fake_resend.Emails.send.call_args[0][0]
    assert payload["from"] == "noreply@test.com"
    assert payload["to"] == ["support@test.com"]
    assert payload["reply_to"] == "alice@example.com"
    assert "[REFUND]" in payload["subject"]
    assert "alice@example.com" in payload["subject"]
    assert "please refund me" in payload["html"]
    assert "job_hunter" in payload["html"]
    assert "fid-1" in payload["html"]


def test_send_feedback_notification_escapes_html_in_message(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-2",
            feedback_type="bug",
            user_email="bob@example.com",
            message="<script>alert(1)</script>",
            context={},
        )

    html = fake_resend.Emails.send.call_args[0][0]["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_send_feedback_notification_omits_reply_to_when_user_email_missing(patched_settings):
    from hr_breaker.services.email_service import EmailService

    with patch("hr_breaker.services.email_service.resend") as fake_resend:
        EmailService().send_feedback_notification(
            feedback_id="fid-3",
            feedback_type="idea",
            user_email=None,
            message="some idea here yes",
            context={},
        )

    payload = fake_resend.Emails.send.call_args[0][0]
    assert "reply_to" not in payload
    assert "no email on file" in payload["html"]
```

**Step 2: Run — expect ImportError / failure**

```bash
uv run pytest tests/test_email_service.py -v
```

Expected: ImportError ("No module named hr_breaker.services.email_service") — that's a fail.

---

## Task 4: Email service — minimal implementation

**Files:**
- Create: `src/hr_breaker/services/email_service.py`

**Step 1: Write the implementation**

```python
"""Resend email wrapper. Used by /api/feedback to notify the support team."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Literal

import resend

from hr_breaker.config import get_settings, logger


FeedbackType = Literal["refund", "bug", "idea"]


class EmailServiceError(Exception):
    """Raised when Resend send fails."""


class EmailService:
    """Thin wrapper over the Resend Python SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        resend.api_key = settings.resend_api_key
        self._from = settings.support_email_from
        self._to = settings.support_email_to

    def send_feedback_notification(
        self,
        *,
        feedback_id: str,
        feedback_type: FeedbackType,
        user_email: str | None,
        message: str,
        context: dict,
    ) -> None:
        subject = f"[{feedback_type.upper()}] from {user_email or 'unknown user'}"
        body_html = _render_feedback_html(
            feedback_id=feedback_id,
            feedback_type=feedback_type,
            user_email=user_email,
            message=message,
            context=context,
        )

        payload: dict = {
            "from": self._from,
            "to": [self._to],
            "subject": subject,
            "html": body_html,
        }
        if user_email:
            payload["reply_to"] = user_email

        try:
            resend.Emails.send(payload)
        except Exception as e:  # SDK can raise various exceptions
            logger.warning("Resend send failed for feedback %s: %s", feedback_id, e)
            raise EmailServiceError(str(e)) from e


def _render_feedback_html(
    *,
    feedback_id: str,
    feedback_type: str,
    user_email: str | None,
    message: str,
    context: dict,
) -> str:
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_message = html.escape(message)
    user_line = (
        html.escape(user_email) if user_email else "no email on file"
    )

    context_lines = []
    for key in ("tier", "status", "current_period_end", "stripe_customer_id"):
        value = context.get(key)
        if value is not None:
            context_lines.append(
                f"  {html.escape(key)}: {html.escape(str(value))}"
            )
    context_block = "\n".join(context_lines) or "  (no subscription context)"

    return (
        f"<pre style='font-family: ui-monospace, monospace; font-size: 13px;'>"
        f"Type: {html.escape(feedback_type)}\n"
        f"User: {user_line}\n"
        f"Submitted: {submitted_at}\n"
        f"Feedback ID: {html.escape(feedback_id)}\n\n"
        f"Subscription context:\n{context_block}\n\n"
        f"Message:\n"
        f"─────────────────────────────────\n"
        f"{safe_message}\n"
        f"─────────────────────────────────\n\n"
        f"Reply directly to this email — it goes to the user.</pre>"
    )
```

**Step 2: Run tests — expect pass**

```bash
uv run pytest tests/test_email_service.py -v
```

Expected: 3 passed.

**Step 3: Commit**

```bash
git add src/hr_breaker/services/email_service.py tests/test_email_service.py
git commit -m "feat(feedback): add EmailService with Resend integration"
```

---

## Task 5: Feedback API route — failing tests

**Files:**
- Create: `tests/test_feedback_routes.py`

**Step 1: Write tests**

Mirror the structure of `tests/test_coach_routes.py` (TestClient + dependency_overrides).

```python
"""Tests for /api/feedback route."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user_email,
    get_supabase_service,
)
from hr_breaker.api.main import app

USER = "user-uuid"
EMAIL = "user@example.com"


def _profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "job_hunter",
        "subscription_status": "active",
        "current_period_end": "2099-01-01T00:00:00+00:00",
        "stripe_customer_id": "cus_test",
    }


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_profile.return_value = _profile()
    # supabase.client.table(...).insert(...).execute() returns
    # an object with .data = [{"id": "fid-x", ...}]
    insert_chain = MagicMock()
    insert_chain.execute.return_value = MagicMock(data=[{"id": "fid-x"}])
    table_mock = MagicMock()
    table_mock.insert.return_value = insert_chain
    # Rate limit query: select(...).eq(...).gte(...).execute() with count=0
    select_chain = MagicMock()
    select_chain.eq.return_value.gte.return_value.execute.return_value = MagicMock(count=0)
    table_mock.select.return_value = select_chain
    # Update chain for email_sent_at
    update_chain = MagicMock()
    update_chain.eq.return_value.execute.return_value = MagicMock(data=[])
    table_mock.update.return_value = update_chain
    svc.client.table.return_value = table_mock
    svc._table_mock = table_mock  # for assertions
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user_email] = lambda: (USER, EMAIL)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_submit_feedback_creates_row_and_sends_email(client, fake_supabase):
    with patch("hr_breaker.api.routes.feedback.EmailService") as fake_email_cls:
        instance = fake_email_cls.return_value
        resp = client.post(
            "/api/feedback",
            json={"type": "refund", "message": "please refund my last payment"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # INSERT happened with type, user_id, message, context
    insert_call = fake_supabase._table_mock.insert.call_args[0][0]
    assert insert_call["type"] == "refund"
    assert insert_call["user_id"] == USER
    assert insert_call["message"] == "please refund my last payment"
    assert insert_call["context"]["tier"] == "job_hunter"
    assert insert_call["context"]["user_email"] == EMAIL
    # Email sent
    instance.send_feedback_notification.assert_called_once()
    # email_sent_at updated
    fake_supabase._table_mock.update.assert_called_once()


def test_submit_feedback_too_short_returns_422(client):
    resp = client.post("/api/feedback", json={"type": "bug", "message": "short"})
    assert resp.status_code == 422


def test_submit_feedback_too_long_returns_422(client):
    resp = client.post(
        "/api/feedback",
        json={"type": "bug", "message": "x" * 4001},
    )
    assert resp.status_code == 422


def test_submit_feedback_invalid_type_returns_422(client):
    resp = client.post(
        "/api/feedback",
        json={"type": "spam", "message": "valid length message here"},
    )
    assert resp.status_code == 422


def test_submit_feedback_unauthenticated_returns_401():
    # Don't override deps — real auth applies
    app.dependency_overrides.clear()
    c = TestClient(app)
    resp = c.post(
        "/api/feedback",
        json={"type": "idea", "message": "some valid idea here"},
    )
    assert resp.status_code == 401


def test_rate_limit_after_5_requests_returns_429(client, fake_supabase):
    # Override count to simulate 5 prior submissions in last hour
    fake_supabase.client.table.return_value.select.return_value.eq.return_value.gte.return_value.execute.return_value = MagicMock(count=5)
    with patch("hr_breaker.api.routes.feedback.EmailService"):
        resp = client.post(
            "/api/feedback",
            json={"type": "idea", "message": "some valid idea text here"},
        )
    assert resp.status_code == 429


def test_email_failure_still_persists_and_returns_200(client, fake_supabase):
    from hr_breaker.services.email_service import EmailServiceError

    with patch("hr_breaker.api.routes.feedback.EmailService") as fake_email_cls:
        fake_email_cls.return_value.send_feedback_notification.side_effect = (
            EmailServiceError("resend down")
        )
        resp = client.post(
            "/api/feedback",
            json={"type": "bug", "message": "something broke for me"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # INSERT still happened
    fake_supabase._table_mock.insert.assert_called_once()
    # email_sent_at NOT updated (no successful send)
    fake_supabase._table_mock.update.assert_not_called()


def test_message_is_stripped(client, fake_supabase):
    with patch("hr_breaker.api.routes.feedback.EmailService"):
        resp = client.post(
            "/api/feedback",
            json={"type": "idea", "message": "   leading and trailing whitespace here   "},
        )
    assert resp.status_code == 200
    insert_call = fake_supabase._table_mock.insert.call_args[0][0]
    assert insert_call["message"] == "leading and trailing whitespace here"
```

**Step 2: Run — expect failure**

```bash
uv run pytest tests/test_feedback_routes.py -v
```

Expected: ImportError on `hr_breaker.api.routes.feedback`.

---

## Task 6: Feedback API route — implementation

**Files:**
- Create: `src/hr_breaker/api/routes/feedback.py`
- Modify: `src/hr_breaker/api/routes/__init__.py`
- Modify: `src/hr_breaker/api/main.py`

**Step 1: Write the route**

```python
"""User feedback endpoint — refund / bug / idea submissions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from hr_breaker.api.deps import CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.config import logger
from hr_breaker.services.email_service import EmailService, EmailServiceError

router = APIRouter()

RATE_LIMIT_WINDOW = timedelta(hours=1)
RATE_LIMIT_MAX = 5


class FeedbackRequest(BaseModel):
    type: Literal["refund", "bug", "idea"]
    message: str = Field(min_length=10, max_length=4000)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Message must be at least 10 characters")
        return v


class FeedbackResponse(BaseModel):
    ok: bool


def _build_context(profile: dict, user_email: str | None) -> dict:
    return {
        "tier": profile.get("subscription_tier"),
        "status": profile.get("subscription_status"),
        "current_period_end": profile.get("current_period_end"),
        "stripe_customer_id": profile.get("stripe_customer_id"),
        "user_email": user_email,
    }


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
) -> FeedbackResponse:
    user_id, user_email = user

    # Rate limit
    window_start = (datetime.now(timezone.utc) - RATE_LIMIT_WINDOW).isoformat()
    recent = (
        supabase.client.table("user_feedback")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", window_start)
        .execute()
    )
    if (recent.count or 0) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail="Too many feedback submissions, try again later",
        )

    profile = supabase.get_profile(user_id) or {}
    context = _build_context(profile, user_email)

    insert_result = (
        supabase.client.table("user_feedback")
        .insert(
            {
                "user_id": user_id,
                "type": body.type,
                "message": body.message,
                "context": context,
            }
        )
        .execute()
    )
    feedback_id = insert_result.data[0]["id"]

    try:
        EmailService().send_feedback_notification(
            feedback_id=feedback_id,
            feedback_type=body.type,
            user_email=user_email,
            message=body.message,
            context=context,
        )
        supabase.client.table("user_feedback").update(
            {"email_sent_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", feedback_id).execute()
    except EmailServiceError as e:
        # Persistence already happened; log and return success.
        logger.warning(
            "Feedback %s saved but email failed: %s", feedback_id, e
        )

    return FeedbackResponse(ok=True)
```

**Step 2: Register the router**

Modify `src/hr_breaker/api/routes/__init__.py` — add the import and `__all__` entry:

```python
from .feedback import router as feedback_router
```

…and add `"feedback_router",` to the `__all__` list (alphabetical, after `editor_router`).

Modify `src/hr_breaker/api/main.py` — add the import inside the existing block:

```python
from hr_breaker.api.routes import (
    coach_router,
    cvs_router,
    editor_router,
    feedback_router,  # NEW
    optimize_router,
    subscription_router,
    telegram_router,
    users_router,
    webhooks_router,
)
```

…and register it after the `subscription_router` line:

```python
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
```

**Step 3: Run feedback tests — expect pass**

```bash
uv run pytest tests/test_feedback_routes.py -v
```

Expected: 8 passed.

**Step 4: Run full test suite — make sure nothing else broke**

```bash
uv run pytest -x
```

Expected: all passing.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/feedback.py src/hr_breaker/api/routes/__init__.py src/hr_breaker/api/main.py tests/test_feedback_routes.py
git commit -m "feat(feedback): POST /api/feedback with rate limit and resilient email"
```

---

## Task 7: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Add types**

Inspect `frontend/src/types/index.ts` first to find a logical place to insert (probably near the bottom). Add:

```ts
export type FeedbackType = "refund" | "bug" | "idea";

export interface FeedbackRequest {
  type: FeedbackType;
  message: string;
}

export interface FeedbackResponse {
  ok: boolean;
}
```

**Step 2: Add the API call**

In `frontend/src/lib/api.ts`, import the types in the existing import block:

```ts
  FeedbackRequest,
  FeedbackResponse,
```

Then at the end of the file (or grouped with subscription helpers), add:

```ts
export async function submitFeedback(
  body: FeedbackRequest,
): Promise<FeedbackResponse> {
  return fetchWithAuth<FeedbackResponse>("/feedback", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
```

**Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit && cd ..
```

Expected: no TS errors.

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(feedback): frontend types and submitFeedback api"
```

---

## Task 8: SupportCard component

**Files:**
- Create: `frontend/src/app/(protected)/settings/_components/SupportCard.tsx`

**Step 1: Inspect what's reusable**

Quickly skim `frontend/src/components/ui/tabs.tsx` to confirm the API (it's standard shadcn — `<Tabs>`, `<TabsList>`, `<TabsTrigger>`, `<TabsContent>`).

**Step 2: Write the component**

```tsx
"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Check, AlertCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { submitFeedback, getSubscriptionStatus } from "@/lib/api";
import type { FeedbackType, SubscriptionStatus } from "@/types";

const PLACEHOLDERS: Record<FeedbackType, string> = {
  refund: "Reason for refund + which payment...",
  bug: "What happened? Steps to reproduce...",
  idea: "What would make HR-Breaker better for you?",
};

const MAX_LEN = 4000;
const MIN_LEN = 10;

function formatPeriodEnd(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "long" }).format(
    new Date(iso),
  );
}

export function SupportCard() {
  const [type, setType] = useState<FeedbackType>("refund");
  const [message, setMessage] = useState("");
  const [justSent, setJustSent] = useState(false);

  const { data: subscription } = useQuery<SubscriptionStatus>({
    queryKey: ["subscription"],
    queryFn: getSubscriptionStatus,
  });

  const mutation = useMutation({
    mutationFn: submitFeedback,
    onSuccess: () => {
      setMessage("");
      setJustSent(true);
      setTimeout(() => setJustSent(false), 30_000);
    },
  });

  const trimmed = message.trim();
  const valid = trimmed.length >= MIN_LEN && trimmed.length <= MAX_LEN;
  const disabled = !valid || mutation.isPending || justSent;

  const handleSubmit = () => {
    mutation.mutate({ type, message: trimmed });
  };

  const periodEnd = formatPeriodEnd(subscription?.current_period_end ?? null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Support / Feedback</CardTitle>
        <CardDescription>
          Refund requests, bug reports, and ideas — we read every one.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Tabs
          value={type}
          onValueChange={(v) => setType(v as FeedbackType)}
        >
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="refund">Refund</TabsTrigger>
            <TabsTrigger value="bug">Bug</TabsTrigger>
            <TabsTrigger value="idea">Idea</TabsTrigger>
          </TabsList>
        </Tabs>

        {type === "refund" && subscription && (
          <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            Current plan: <span className="font-medium">{subscription.tier}</span>
            {periodEnd && <> · renews {periodEnd}</>}
          </div>
        )}

        <div className="space-y-1">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={PLACEHOLDERS[type]}
            maxLength={MAX_LEN}
            rows={5}
            className="flex w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={mutation.isPending || justSent}
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{trimmed.length < MIN_LEN ? `Min ${MIN_LEN} chars` : ""}</span>
            <span>
              {message.length}/{MAX_LEN}
            </span>
          </div>
        </div>

        {mutation.isError && (
          <div className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Failed to send: {(mutation.error as Error)?.message ?? "Unknown error"}
            </span>
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          {justSent && (
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <Check className="h-4 w-4 text-green-600" />
              Sent — we&apos;ll reach out via email
            </span>
          )}
          <Button onClick={handleSubmit} disabled={disabled}>
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Sending...
              </>
            ) : (
              "Send"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit && cd ..
```

Expected: no TS errors.

**Step 4: Commit**

```bash
git add frontend/src/app/\(protected\)/settings/_components/SupportCard.tsx
git commit -m "feat(feedback): SupportCard component"
```

---

## Task 9: Wire SupportCard into /settings

**Files:**
- Modify: `frontend/src/app/(protected)/settings/page.tsx`

**Step 1: Add import**

In the imports block of `page.tsx` (near the top, alongside the existing local imports), add:

```tsx
import { SupportCard } from "./_components/SupportCard";
```

**Step 2: Render below SubscriptionCard**

Find `<SubscriptionCard />` in the JSX and add the new card right after it:

```tsx
      <SubscriptionCard />

      <SupportCard />
```

**Step 3: Type-check and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint && cd ..
```

Expected: clean.

**Step 4: Manual smoke test**

Start the API and frontend in two terminals (PowerShell):

```powershell
# Terminal 1 (API)
uv run uvicorn hr_breaker.api.main:app --reload

# Terminal 2 (Frontend)
cd frontend; npm run dev
```

Open http://localhost:3000/settings, scroll to "Support / Feedback":
- Tabs switch placeholder text and show/hide the subscription strip on Refund.
- Submit with <10 chars: button stays disabled.
- Submit with valid text: spinner → green check → form clears, button greyed for 30s.
- Without `RESEND_API_KEY` set, the API still returns 200 (saved in DB, email skipped).

Note: the user can verify the row landed in Supabase via Studio if Supabase is configured locally.

**Step 5: Commit**

```bash
git add frontend/src/app/\(protected\)/settings/page.tsx
git commit -m "feat(feedback): mount SupportCard on /settings"
```

---

## Task 10: Final verification

**Step 1: Run full Python tests**

```bash
uv run pytest
```

Expected: all green.

**Step 2: Lint frontend**

```bash
cd frontend && npm run lint && cd ..
```

Expected: no errors.

**Step 3: Confirm migration is in tree**

```bash
git log --oneline -10
```

Should show the chain of commits from Task 1 through 9 on `dev`.

---

## Out of scope (do not add)

- User-facing history list of past submissions.
- Stripe automatic refund.
- Background job / retry for failed Resend sends.
- Telegram fallback notification.
- Toast library — inline success state is sufficient.
- Attachments / file upload.

These are documented as "future work" in the design doc.
