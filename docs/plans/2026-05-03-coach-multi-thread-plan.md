# Coach Multi-Thread Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-thread-per-position Coach with a multi-thread sidebar UX that loads full message history when returning to a thread.

**Architecture:** Drop `UNIQUE(user_id, optimization_run_id)`, add `title` and `last_message_at` columns to `coach_sessions`. Backend exposes `thread_id` in API; lazy-creates threads on first message. Frontend replaces the position `<select>` with a hierarchical sidebar (web) / drawer (mobile), drives active thread via `?threadId=` URL param, and persists the last-viewed thread to `localStorage`.

**Tech Stack:** PostgreSQL (Supabase migration), FastAPI + Pydantic, pytest with `TestClient`, Next.js App Router, React Query, Tailwind. No frontend test infra — frontend tasks verified via build + manual e2e.

**Reference design:** `docs/plans/2026-05-03-coach-multi-thread-design.md`

---

## Phase 1 — Database

### Task 1: Write migration `015_coach_threads.sql`

**Files:**
- Create: `supabase/migrations/015_coach_threads.sql`

**Step 1: Write the migration**

```sql
-- 015_coach_threads.sql — multi-thread support for Coach.

-- Allow multiple threads per (user, optimization_run).
ALTER TABLE coach_sessions
    DROP CONSTRAINT IF EXISTS coach_sessions_user_id_optimization_run_id_key;

-- Optional manual title; NULL = frontend uses preview fallback.
ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS title VARCHAR(255);

-- Activity timestamp used for sidebar sort and "last active thread".
ALTER TABLE coach_sessions
    ADD COLUMN IF NOT EXISTS last_message_at TIMESTAMPTZ;

-- Backfill so existing rows sort correctly in the new sidebar.
UPDATE coach_sessions
   SET last_message_at = updated_at
 WHERE last_message_at IS NULL;

-- Composite index for sidebar grouping query.
CREATE INDEX IF NOT EXISTS idx_coach_sessions_user_run
    ON coach_sessions(user_id, optimization_run_id, last_message_at DESC);
```

**Step 2: Apply locally**

Run: `supabase db push` (or whatever the project uses — check `README.md` "Supabase Setup").
Expected: migration applies, no errors. Verify in Supabase dashboard that:
- `coach_sessions_user_id_optimization_run_id_key` constraint is gone.
- `title` and `last_message_at` columns exist.
- `idx_coach_sessions_user_run` index exists.

**Step 3: Commit**

```bash
git add supabase/migrations/015_coach_threads.sql
git commit -m "feat(db): coach_sessions multi-thread schema"
```

---

## Phase 2 — Backend (Supabase service + schemas)

### Task 2: Update Supabase service methods

**Files:**
- Modify: `src/hr_breaker/services/supabase.py:319-405`

**Step 1: Replace `get_or_create_coach_session` with split methods**

Remove `get_or_create_coach_session`. Add:

```python
def create_coach_session(
    self,
    user_id: str,
    optimization_run_id: str,
) -> dict[str, Any]:
    """Create a new coach session (thread)."""
    try:
        session_id = str(uuid4())
        result = (
            self._client.table("coach_sessions")
            .insert({
                "id": session_id,
                "user_id": user_id,
                "optimization_run_id": optimization_run_id,
            })
            .execute()
        )
        return result.data[0]
    except Exception as e:
        logger.error(f"Failed to create coach session: {e}")
        raise SupabaseError(f"Failed to create coach session: {e}") from e

def get_coach_session(
    self, session_id: str, user_id: str
) -> dict[str, Any] | None:
    """Return coach session if it belongs to user, else None."""
    try:
        result = (
            self._client.table("coach_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to get coach session: {e}")
        raise SupabaseError(f"Failed to get coach session: {e}") from e

def update_coach_session_title(
    self, session_id: str, user_id: str, title: str | None
) -> dict[str, Any] | None:
    """Update session title with ownership check."""
    try:
        result = (
            self._client.table("coach_sessions")
            .update({"title": title})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to update coach session: {e}")
        raise SupabaseError(f"Failed to update coach session: {e}") from e

def delete_coach_session(self, session_id: str, user_id: str) -> bool:
    """Delete coach session (cascades to messages). Returns True if removed."""
    try:
        result = (
            self._client.table("coach_sessions")
            .delete()
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        logger.error(f"Failed to delete coach session: {e}")
        raise SupabaseError(f"Failed to delete coach session: {e}") from e
```

**Step 2: Update `list_coach_sessions` to include preview + counts**

Replace the existing method body so it returns the fields the new sidebar needs:

```python
def list_coach_sessions(self, user_id: str) -> list[dict[str, Any]]:
    """List all coach sessions for a user with preview + message_count."""
    try:
        sessions = (
            self._client.table("coach_sessions")
            .select("id, optimization_run_id, title, last_message_at, created_at, updated_at")
            .eq("user_id", user_id)
            .order("last_message_at", desc=True, nullsfirst=False)
            .execute()
        ).data

        if not sessions:
            return []

        # Bulk-fetch messages for all sessions in one round-trip.
        ids = [s["id"] for s in sessions]
        msg_rows = (
            self._client.table("coach_messages")
            .select("session_id, messages")
            .in_("session_id", ids)
            .execute()
        ).data
        by_session = {row["session_id"]: row.get("messages") or [] for row in msg_rows}

        for s in sessions:
            raw = by_session.get(s["id"], [])
            preview, count = _preview_and_count(raw)
            s["preview"] = preview
            s["message_count"] = count
        return sessions
    except Exception as e:
        logger.error(f"Failed to list coach sessions: {e}")
        raise SupabaseError(f"Failed to list coach sessions: {e}") from e
```

Add a module-level helper above `SupabaseService`:

```python
def _preview_and_count(raw_messages: list) -> tuple[str | None, int]:
    """Return (first user message preview, total user+assistant count)."""
    from pydantic_ai import ModelMessagesTypeAdapter
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    if not raw_messages:
        return None, 0
    try:
        messages = ModelMessagesTypeAdapter.validate_python(raw_messages)
    except Exception:
        return None, 0

    preview = None
    count = 0
    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart):
                    count += 1
                    if preview is None:
                        text = part.content if isinstance(part.content, str) else str(part.content)
                        preview = text.strip()[:80] or None
        elif isinstance(msg, ModelResponse):
            if any(isinstance(p, TextPart) for p in msg.parts):
                count += 1
    return preview, count
```

**Step 3: Update `save_coach_messages` to also touch `last_message_at`**

In `save_coach_messages` (around line 399-402), change the session-touch block to set both `updated_at` and `last_message_at`:

```python
self._client.table("coach_sessions").update(
    {"updated_at": now, "last_message_at": now}
).eq("id", session_id).execute()
```

**Step 4: Manual sanity check**

Run: `uv run python -c "from hr_breaker.services.supabase import SupabaseService"`
Expected: imports cleanly, no syntax errors.

**Step 5: Commit**

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "feat(supabase): coach session CRUD + preview/count in list"
```

---

### Task 3: Update API schemas

**Files:**
- Modify: `src/hr_breaker/api/schemas.py:146-167`

**Step 1: Replace coach schemas**

```python
class CoachChatRequest(BaseModel):
    """Send a message to the coach. Provide either thread_id (existing) or
    optimization_run_id (lazy-create new thread)."""

    thread_id: str | None = None
    optimization_run_id: str | None = None
    message: str

    @model_validator(mode="after")
    def _exactly_one_target(self):
        has_thread = self.thread_id is not None
        has_run = self.optimization_run_id is not None
        if has_thread == has_run:
            raise ValueError("Provide exactly one of thread_id or optimization_run_id")
        return self


class CoachThreadCreateRequest(BaseModel):
    """Create an empty thread for a position."""

    optimization_run_id: str


class CoachThreadUpdateRequest(BaseModel):
    """Rename a thread. title=None clears the manual title."""

    title: str | None = None


class CoachSessionResponse(BaseModel):
    """Coach session info for the sidebar."""

    id: str
    optimization_run_id: str
    title: str | None = None
    last_message_at: str | None = None
    message_count: int = 0
    preview: str | None = None
    created_at: str
    updated_at: str


class CoachMessageResponse(BaseModel):
    role: str
    content: str
```

Add `model_validator` to imports:

```python
from pydantic import BaseModel, Field, model_validator
```

**Step 2: Verify import**

Run: `uv run python -c "from hr_breaker.api.schemas import CoachChatRequest, CoachThreadCreateRequest, CoachThreadUpdateRequest, CoachSessionResponse"`
Expected: clean import.

**Step 3: Commit**

```bash
git add src/hr_breaker/api/schemas.py
git commit -m "feat(api): coach thread schemas (create/update/preview)"
```

---

## Phase 3 — Backend (routes + tests)

### Task 4: Bootstrap test scaffolding for coach routes

**Files:**
- Create: `tests/test_coach_routes.py`

**Step 1: Write skeleton**

```python
"""Tests for /api/coach routes — multi-thread."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import (
    get_current_user_id,
    get_supabase_service,
    require_feature,
)
from hr_breaker.api.main import app
from hr_breaker.services.tiers import Feature

USER = "user-uuid"


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.list_coach_sessions.return_value = []
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user_id] = lambda: USER
    app.dependency_overrides[require_feature(Feature.COACH)] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_sessions_returns_preview_and_counts(client, fake_supabase):
    fake_supabase.list_coach_sessions.return_value = [
        {
            "id": "s1",
            "optimization_run_id": "r1",
            "title": None,
            "last_message_at": "2026-05-03T10:00:00Z",
            "created_at": "2026-05-01T10:00:00Z",
            "updated_at": "2026-05-03T10:00:00Z",
            "preview": "tell me about a time...",
            "message_count": 4,
        }
    ]
    r = client.get("/api/coach/sessions")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["preview"] == "tell me about a time..."
    assert body[0]["message_count"] == 4
    assert body[0]["title"] is None
```

**Step 2: Run, expecting failures we'll fix in next tasks**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: depending on current state of `list_coach_sessions` route response, this may pass already (route is unchanged) but the schema `CoachSessionResponse` doesn't yet have `preview`. If it fails, it's because the schema validation drops unknown fields — we'll fix in next task.

**Step 3: Commit**

```bash
git add tests/test_coach_routes.py
git commit -m "test(coach): scaffold multi-thread route tests"
```

> Note for executor: confirm `get_current_user_id` and `require_feature(Feature.COACH)` are the actual dep names by reading `src/hr_breaker/api/deps.py` first. Adjust import names if different.

---

### Task 5: Update `/sessions` route to use new schema

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py:64-67`

**Step 1: Update route**

The Pydantic `response_model=list[CoachSessionResponse]` will now validate the new fields. No code change needed if the service already returns them, but verify imports include the new schema names.

**Step 2: Run test**

Run: `uv run pytest tests/test_coach_routes.py::test_list_sessions_returns_preview_and_counts -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add -u
git commit -m "feat(coach): list sessions returns preview + counts"
```

---

### Task 6: Add POST /sessions (create empty thread) — write failing test

**Files:**
- Modify: `tests/test_coach_routes.py`

**Step 1: Add test**

```python
def test_create_thread_returns_session(client, fake_supabase):
    fake_supabase.create_coach_session.return_value = {
        "id": "new-id",
        "optimization_run_id": "r1",
        "title": None,
        "last_message_at": None,
        "created_at": "2026-05-03T10:00:00Z",
        "updated_at": "2026-05-03T10:00:00Z",
    }
    r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "new-id"
    assert body["message_count"] == 0
    assert body["preview"] is None
    fake_supabase.create_coach_session.assert_called_once_with(USER, "r1")
```

**Step 2: Run, expect 404 / method not allowed**

Run: `uv run pytest tests/test_coach_routes.py::test_create_thread_returns_session -v`
Expected: FAIL (route doesn't exist).

---

### Task 7: Implement POST /sessions

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py`

**Step 1: Add route + import schema**

```python
from hr_breaker.api.schemas import (
    ...,
    CoachThreadCreateRequest,
    CoachThreadUpdateRequest,
)


@router.post("/sessions", response_model=CoachSessionResponse, status_code=201)
async def create_thread(
    body: CoachThreadCreateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Create an empty coach thread for a position."""
    # Verify the optimization_run belongs to the user.
    run = supabase.get_optimization_run(body.optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    session = supabase.create_coach_session(user_id, body.optimization_run_id)
    return {**session, "preview": None, "message_count": 0}
```

**Step 2: Run test**

Run: `uv run pytest tests/test_coach_routes.py::test_create_thread_returns_session -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add tests/test_coach_routes.py src/hr_breaker/api/routes/coach.py
git commit -m "feat(coach): POST /sessions creates empty thread"
```

---

### Task 8: PATCH /sessions/{id} (rename) — test + implement

**Files:**
- Modify: `tests/test_coach_routes.py`, `src/hr_breaker/api/routes/coach.py`

**Step 1: Add tests**

```python
def test_rename_thread_updates_title(client, fake_supabase):
    fake_supabase.update_coach_session_title.return_value = {
        "id": "s1",
        "optimization_run_id": "r1",
        "title": "STAR conflict story",
        "last_message_at": "2026-05-03T10:00:00Z",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-03T10:05:00Z",
    }
    r = client.patch("/api/coach/sessions/s1", json={"title": "STAR conflict story"})
    assert r.status_code == 200
    assert r.json()["title"] == "STAR conflict story"
    fake_supabase.update_coach_session_title.assert_called_once_with(
        "s1", USER, "STAR conflict story"
    )


def test_rename_other_users_thread_returns_404(client, fake_supabase):
    fake_supabase.update_coach_session_title.return_value = None
    r = client.patch("/api/coach/sessions/foreign", json={"title": "x"})
    assert r.status_code == 404
```

**Step 2: Run, expect FAIL**

Run: `uv run pytest tests/test_coach_routes.py -k rename -v`
Expected: FAIL.

**Step 3: Implement**

```python
@router.patch("/sessions/{session_id}", response_model=CoachSessionResponse)
async def rename_thread(
    session_id: str,
    body: CoachThreadUpdateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    updated = supabase.update_coach_session_title(session_id, user_id, body.title)
    if not updated:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {**updated, "preview": None, "message_count": 0}
```

**Step 4: Run, expect PASS**

Run: `uv run pytest tests/test_coach_routes.py -k rename -v`

**Step 5: Commit**

```bash
git add -u
git commit -m "feat(coach): PATCH /sessions/{id} rename"
```

---

### Task 9: DELETE /sessions/{id} — test + implement

**Files:** same as Task 8.

**Step 1: Tests**

```python
def test_delete_thread_returns_204(client, fake_supabase):
    fake_supabase.delete_coach_session.return_value = True
    r = client.delete("/api/coach/sessions/s1")
    assert r.status_code == 204
    fake_supabase.delete_coach_session.assert_called_once_with("s1", USER)


def test_delete_other_users_thread_returns_404(client, fake_supabase):
    fake_supabase.delete_coach_session.return_value = False
    r = client.delete("/api/coach/sessions/foreign")
    assert r.status_code == 404
```

**Step 2: FAIL**

Run: `uv run pytest tests/test_coach_routes.py -k delete -v`

**Step 3: Implement**

```python
@router.delete("/sessions/{session_id}", status_code=204)
async def delete_thread(
    session_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    if not supabase.delete_coach_session(session_id, user_id):
        raise HTTPException(status_code=404, detail="Thread not found")
```

**Step 4: PASS + commit**

```bash
git add -u
git commit -m "feat(coach): DELETE /sessions/{id}"
```

---

### Task 10: Rework `/chat` to accept thread_id and lazy-create

**Files:** `tests/test_coach_routes.py`, `src/hr_breaker/api/routes/coach.py`

**Step 1: Tests**

Add to test file:

```python
def test_chat_validates_exactly_one_target(client):
    # Both → 422
    r = client.post(
        "/api/coach/chat",
        json={"thread_id": "t", "optimization_run_id": "r", "message": "hi"},
    )
    assert r.status_code == 422
    # Neither → 422
    r = client.post("/api/coach/chat", json={"message": "hi"})
    assert r.status_code == 422
```

**Step 2: Run, expect at least one to fail (current schema rejects no `optimization_run_id`)**

Run: `uv run pytest tests/test_coach_routes.py -k chat_validates -v`

**Step 3: Update `/chat` route**

Replace the start of `chat()` (lines 89-117) with:

```python
@router.post("/chat")
async def chat(
    body: CoachChatRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Stream a coach response via SSE.

    Either body.thread_id (existing thread) or body.optimization_run_id
    (lazy-create new thread). Validated by CoachChatRequest.
    """
    # Resolve thread.
    if body.thread_id:
        session = supabase.get_coach_session(body.thread_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Thread not found")
        optimization_run_id = session["optimization_run_id"]
    else:
        # Lazy create.
        session = supabase.create_coach_session(user_id, body.optimization_run_id)
        optimization_run_id = body.optimization_run_id

    session_id = session["id"]

    # Load optimization run for context.
    run = supabase.get_optimization_run(optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    job_parsed = run.get("job_parsed") or {}
    # ... (keep the rest of the function — cv_text load, storybank, history,
    # deps, agent, event_stream — unchanged)
```

In the `done` SSE event (lines 152-154), the existing code already returns `session_id`. Rename the JSON key to `thread_id` for consistency:

```python
done = json.dumps({"type": "done", "thread_id": session_id})
yield f"data: {done}\n\n"
```

**Step 4: Run, expect PASS**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: all coach tests pass.

**Step 5: Commit**

```bash
git add tests/test_coach_routes.py src/hr_breaker/api/routes/coach.py
git commit -m "feat(coach): /chat accepts thread_id with lazy create"
```

---

## Phase 4 — Frontend types + API client

### Task 11: Update TypeScript types

**Files:**
- Modify: `frontend/src/types/index.ts:144-167`

**Step 1: Replace Coach types**

```ts
// Coach types
export interface CoachSession {
  id: string;
  optimization_run_id: string;
  title: string | null;
  last_message_at: string | null;
  message_count: number;
  preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoachMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CoachChatRequest {
  message: string;
  thread_id?: string;
  optimization_run_id?: string;
}

export interface CoachSSEEvent {
  type: "delta" | "done" | "error";
  content?: string;
  thread_id?: string;
}
```

**Step 2: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors in `lib/api.ts`, `hooks/useCoach.ts`, `app/(protected)/coach/page.tsx` — these are the call sites we'll update next.

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "refactor(types): coach session multi-thread fields"
```

---

### Task 12: Update API client

**Files:**
- Modify: `frontend/src/lib/api.ts:251-313`

**Step 1: Update `streamCoachChat` and add CRUD functions**

```ts
// Coach API
export async function listCoachSessions(): Promise<CoachSession[]> {
  return fetchWithAuth<CoachSession[]>("/coach/sessions");
}

export async function getCoachMessages(threadId: string): Promise<CoachMessage[]> {
  return fetchWithAuth<CoachMessage[]>(`/coach/sessions/${threadId}/messages`);
}

export async function createCoachThread(
  optimizationRunId: string,
): Promise<CoachSession> {
  return fetchWithAuth<CoachSession>("/coach/sessions", {
    method: "POST",
    body: JSON.stringify({ optimization_run_id: optimizationRunId }),
  });
}

export async function renameCoachThread(
  threadId: string,
  title: string | null,
): Promise<CoachSession> {
  return fetchWithAuth<CoachSession>(`/coach/sessions/${threadId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteCoachThread(threadId: string): Promise<void> {
  await fetchWithAuth(`/coach/sessions/${threadId}`, { method: "DELETE" });
}

export async function streamCoachChat(
  args: { threadId: string } | { optimizationRunId: string },
  message: string,
  onDelta: (text: string) => void = () => {},
  onDone: (threadId: string) => void = () => {},
  onError: (error: string) => void = () => {},
): Promise<void> {
  const headers = await getAuthHeaders();
  const body: Record<string, unknown> = { message };
  if ("threadId" in args) body.thread_id = args.threadId;
  else body.optimization_run_id = args.optimizationRunId;

  const response = await fetch(`${API_BASE}/coach/chat`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Chat failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const event = JSON.parse(line.slice(6));
        if (event.type === "delta") onDelta(event.content || "");
        else if (event.type === "done") onDone(event.thread_id || "");
        else if (event.type === "error") onError(event.content || "Unknown error");
      } catch {
        /* skip malformed events */
      }
    }
  }
}
```

**Step 2: Verify typecheck of api.ts (still expect errors in hooks/page)**

Run: `cd frontend && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "refactor(api): coach client supports thread_id + CRUD"
```

---

## Phase 5 — Frontend hooks

### Task 13: Rewrite `useCoach.ts`

**Files:**
- Modify: `frontend/src/hooks/useCoach.ts`

**Step 1: Replace contents**

```ts
"use client";

import { useState, useCallback, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCoachThread,
  deleteCoachThread,
  getCoachMessages,
  listCoachSessions,
  renameCoachThread,
  streamCoachChat,
} from "@/lib/api";
import type { CoachMessage, CoachSession } from "@/types";

export function useCoachSessions() {
  return useQuery<CoachSession[]>({
    queryKey: ["coach-sessions"],
    queryFn: listCoachSessions,
    staleTime: 60_000,
  });
}

export function useCoachMessages(threadId: string | null) {
  return useQuery<CoachMessage[]>({
    queryKey: ["coach-messages", threadId],
    queryFn: () => getCoachMessages(threadId!),
    enabled: !!threadId,
    staleTime: 30_000,
  });
}

export function useCreateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (optimizationRunId: string) => createCoachThread(optimizationRunId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["coach-sessions"] }),
  });
}

export function useRenameThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string | null }) =>
      renameCoachThread(threadId, title),
    onMutate: async ({ threadId, title }) => {
      await qc.cancelQueries({ queryKey: ["coach-sessions"] });
      const prev = qc.getQueryData<CoachSession[]>(["coach-sessions"]);
      qc.setQueryData<CoachSession[]>(["coach-sessions"], (old) =>
        old?.map((s) => (s.id === threadId ? { ...s, title } : s)) ?? [],
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["coach-sessions"], ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["coach-sessions"] }),
  });
}

export function useDeleteThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => deleteCoachThread(threadId),
    onSuccess: (_, threadId) => {
      qc.invalidateQueries({ queryKey: ["coach-sessions"] });
      qc.removeQueries({ queryKey: ["coach-messages", threadId] });
    },
  });
}

interface UseCoachChatArgs {
  threadId: string | null;
  optimizationRunId: string | null;
  onThreadCreated: (newThreadId: string) => void;
}

export function useCoachChat({
  threadId,
  optimizationRunId,
  onThreadCreated,
}: UseCoachChatArgs) {
  const qc = useQueryClient();
  const [streamingMessages, setStreamingMessages] = useState<CoachMessage[] | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const inFlightThreadIdRef = useRef<string | null>(null);

  const sendMessage = useCallback(
    async (content: string, baseHistory: CoachMessage[]) => {
      if (isStreaming) return;
      if (!threadId && !optimizationRunId) return;

      inFlightThreadIdRef.current = threadId; // null if first message in lazy thread
      setIsStreaming(true);

      const userMsg: CoachMessage = { role: "user", content };
      const assistantMsg: CoachMessage = { role: "assistant", content: "" };
      setStreamingMessages([...baseHistory, userMsg, assistantMsg]);

      const args = threadId
        ? ({ threadId } as const)
        : ({ optimizationRunId: optimizationRunId! } as const);

      try {
        await streamCoachChat(
          args,
          content,
          (delta) => {
            // Only update UI if user hasn't switched threads.
            const currentInFlight = inFlightThreadIdRef.current;
            if (threadId && currentInFlight !== threadId) return;
            setStreamingMessages((prev) => {
              if (!prev) return prev;
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, content: last.content + delta };
              }
              return updated;
            });
          },
          (newThreadId) => {
            setIsStreaming(false);
            qc.invalidateQueries({ queryKey: ["coach-sessions"] });
            qc.invalidateQueries({ queryKey: ["coach-messages", newThreadId] });
            setStreamingMessages(null);
            if (!threadId) onThreadCreated(newThreadId);
          },
          (err) => {
            setIsStreaming(false);
            setStreamingMessages((prev) => {
              if (!prev) return prev;
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: `Error: ${err}` };
              return updated;
            });
          },
        );
      } catch (e) {
        setIsStreaming(false);
        const msg = e instanceof Error ? e.message : "Unknown error";
        setStreamingMessages((prev) => {
          if (!prev) return prev;
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: `Error: ${msg}` };
          return updated;
        });
      }
    },
    [isStreaming, threadId, optimizationRunId, onThreadCreated, qc],
  );

  return { streamingMessages, isStreaming, sendMessage };
}
```

**Step 2: Verify typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: only errors remaining in `app/(protected)/coach/page.tsx`.

**Step 3: Commit**

```bash
git add frontend/src/hooks/useCoach.ts
git commit -m "refactor(hooks): coach hooks for multi-thread + URL-driven state"
```

---

## Phase 6 — Frontend UI components

### Task 14: Create `ThreadListItem` component

**Files:**
- Create: `frontend/src/components/coach/ThreadListItem.tsx`

**Step 1: Write component**

```tsx
"use client";

import { useState } from "react";
import { MoreVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CoachSession } from "@/types";

interface Props {
  session: CoachSession;
  active: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => void;
  onDelete: () => void;
}

function displayTitle(s: CoachSession): string {
  if (s.title) return s.title;
  if (s.preview) return s.preview.slice(0, 40);
  return "New thread";
}

export function ThreadListItem({ session, active, onSelect, onRename, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.title ?? "");
  const [menuOpen, setMenuOpen] = useState(false);

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => {
          setEditing(false);
          if (draft.trim() && draft !== (session.title ?? "")) onRename(draft.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setDraft(session.title ?? "");
            setEditing(false);
          }
        }}
        className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm"
      />
    );
  }

  return (
    <div
      className={cn(
        "group flex items-center justify-between rounded-md px-2 py-1.5 text-sm cursor-pointer",
        active ? "bg-accent text-accent-foreground" : "hover:bg-muted",
      )}
      onClick={onSelect}
    >
      <span className="truncate flex-1">{displayTitle(session)}</span>
      <div className="relative">
        <button
          type="button"
          className="opacity-0 group-hover:opacity-100 p-1"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((v) => !v);
          }}
          aria-label="Thread actions"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-7 z-10 w-32 rounded-md border border-border bg-popover shadow-md text-sm">
            <button
              className="w-full px-3 py-1.5 text-left hover:bg-muted"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                setEditing(true);
              }}
            >
              Rename
            </button>
            <button
              className="w-full px-3 py-1.5 text-left text-destructive hover:bg-muted"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen(false);
                if (session.message_count === 0 || confirm("Delete thread?")) onDelete();
              }}
            >
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (or only page.tsx errors, which we'll fix later).

**Step 3: Commit**

```bash
git add frontend/src/components/coach/ThreadListItem.tsx
git commit -m "feat(coach): ThreadListItem with rename + delete kebab"
```

---

### Task 15: Create `CoachSidebar` component

**Files:**
- Create: `frontend/src/components/coach/CoachSidebar.tsx`

**Step 1: Write component**

```tsx
"use client";

import { useMemo, useState } from "react";
import { Plus, ChevronDown, ChevronRight } from "lucide-react";
import { ThreadListItem } from "./ThreadListItem";
import type { CoachSession, OptimizationSummary } from "@/types";
import { cn } from "@/lib/utils";

interface Props {
  sessions: CoachSession[];
  positions: OptimizationSummary[];
  activeThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onCreateThreadInPosition: (optimizationRunId: string) => void;
  onAddPosition: () => void;
  onRenameThread: (threadId: string, title: string) => void;
  onDeleteThread: (threadId: string) => void;
}

export function CoachSidebar({
  sessions,
  positions,
  activeThreadId,
  onSelectThread,
  onCreateThreadInPosition,
  onAddPosition,
  onRenameThread,
  onDeleteThread,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");

  const groups = useMemo(() => {
    const positionsById = new Map(positions.map((p) => [p.id, p]));
    const map = new Map<string, { position: OptimizationSummary | null; threads: CoachSession[] }>();
    for (const s of sessions) {
      if (search) {
        const t = (s.title ?? s.preview ?? "").toLowerCase();
        if (!t.includes(search.toLowerCase())) continue;
      }
      const existing = map.get(s.optimization_run_id) ?? {
        position: positionsById.get(s.optimization_run_id) ?? null,
        threads: [],
      };
      existing.threads.push(s);
      map.set(s.optimization_run_id, existing);
    }
    // Sort threads within each group: nulls first, then last_message_at desc.
    for (const g of map.values()) {
      g.threads.sort((a, b) => {
        if (a.last_message_at === null && b.last_message_at !== null) return -1;
        if (a.last_message_at !== null && b.last_message_at === null) return 1;
        if (a.last_message_at === null) return 0;
        return b.last_message_at!.localeCompare(a.last_message_at!);
      });
    }
    return Array.from(map.entries());
  }, [sessions, positions, search]);

  return (
    <div className="flex h-full w-full flex-col border-r border-border bg-background">
      <div className="border-b border-border p-3 space-y-2">
        <input
          type="search"
          placeholder="Search threads"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
        />
        <button
          type="button"
          onClick={onAddPosition}
          className="flex w-full items-center gap-2 rounded-md border border-dashed border-border px-2 py-1.5 text-sm hover:bg-muted"
        >
          <Plus className="h-4 w-4" />
          Add position
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {groups.length === 0 && (
          <div className="text-center text-sm text-muted-foreground p-4">
            No threads yet. Click "Add position" to start.
          </div>
        )}
        {groups.map(([runId, g]) => {
          const isCollapsed = collapsed.has(runId);
          const label = g.position
            ? `${g.position.job_company ?? ""} — ${g.position.job_title ?? ""}`.trim()
            : "Unknown position";
          return (
            <div key={runId}>
              <div className="flex items-center justify-between px-1 py-1 text-xs font-semibold text-muted-foreground">
                <button
                  type="button"
                  onClick={() => {
                    const next = new Set(collapsed);
                    if (next.has(runId)) next.delete(runId);
                    else next.add(runId);
                    setCollapsed(next);
                  }}
                  className="flex flex-1 items-center gap-1 truncate"
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                  <span className="truncate">{label}</span>
                </button>
                <button
                  type="button"
                  onClick={() => onCreateThreadInPosition(runId)}
                  aria-label="New thread in position"
                  className="p-1 hover:bg-muted rounded"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
              {!isCollapsed && (
                <div className={cn("ml-3 space-y-0.5")}>
                  {g.threads.map((t) => (
                    <ThreadListItem
                      key={t.id}
                      session={t}
                      active={t.id === activeThreadId}
                      onSelect={() => onSelectThread(t.id)}
                      onRename={(title) => onRenameThread(t.id, title)}
                      onDelete={() => onDeleteThread(t.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`

**Step 3: Commit**

```bash
git add frontend/src/components/coach/CoachSidebar.tsx
git commit -m "feat(coach): CoachSidebar with grouping + search"
```

---

### Task 16: Create `AddPositionDialog`

**Files:**
- Create: `frontend/src/components/coach/AddPositionDialog.tsx`

**Step 1: Write component**

Minimal modal that lists positions not yet present in `existingPositionIds`, click → calls `onPick(runId)` and closes. Use the project's existing dialog pattern (look at how other modals are built — `frontend/src/components`). If none, fall back to a simple absolute-positioned div with backdrop.

```tsx
"use client";

import { useMemo } from "react";
import type { OptimizationSummary } from "@/types";

interface Props {
  open: boolean;
  positions: OptimizationSummary[];
  existingPositionIds: Set<string>;
  onPick: (runId: string) => void;
  onClose: () => void;
}

export function AddPositionDialog({ open, positions, existingPositionIds, onPick, onClose }: Props) {
  const candidates = useMemo(
    () => positions.filter((p) => !existingPositionIds.has(p.id) && p.status === "complete" && p.job_title),
    [positions, existingPositionIds],
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-lg border border-border bg-background p-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold mb-3">Pick a position</h3>
        {candidates.length === 0 ? (
          <p className="text-sm text-muted-foreground">No positions available — finish an optimization first.</p>
        ) : (
          <ul className="max-h-80 overflow-y-auto divide-y divide-border">
            {candidates.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className="w-full px-2 py-2 text-left text-sm hover:bg-muted rounded"
                  onClick={() => {
                    onPick(p.id);
                    onClose();
                  }}
                >
                  {p.job_company} — {p.job_title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Typecheck + commit**

```bash
cd frontend && npx tsc --noEmit
git add frontend/src/components/coach/AddPositionDialog.tsx
git commit -m "feat(coach): AddPositionDialog picker"
```

---

### Task 17: Create `SidebarDrawer` (mobile wrapper)

**Files:**
- Create: `frontend/src/components/coach/SidebarDrawer.tsx`

**Step 1: Write component**

```tsx
"use client";

import { type ReactNode, useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}

export function SidebarDrawer({ open, onClose, children }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/40 transition-opacity md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />
      <div
        className={`fixed inset-y-0 left-0 z-50 w-[85%] max-w-sm transform bg-background shadow-xl transition-transform md:hidden ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {children}
      </div>
    </>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/coach/SidebarDrawer.tsx
git commit -m "feat(coach): mobile SidebarDrawer wrapper"
```

---

### Task 18: Rewrite `coach/page.tsx`

**Files:**
- Modify: `frontend/src/app/(protected)/coach/page.tsx`

**Step 1: Replace contents**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Menu } from "lucide-react";
import { motion } from "@/components/motion";
import { CoachChat } from "@/components/CoachChat";
import { StorybankPanel } from "@/components/StorybankPanel";
import { UpgradeOverlay } from "@/components/UpgradeOverlay";
import { CoachSidebar } from "@/components/coach/CoachSidebar";
import { SidebarDrawer } from "@/components/coach/SidebarDrawer";
import { AddPositionDialog } from "@/components/coach/AddPositionDialog";
import {
  useCoachChat,
  useCoachMessages,
  useCoachSessions,
  useCreateThread,
  useDeleteThread,
  useRenameThread,
} from "@/hooks/useCoach";
import { useStorybank } from "@/hooks/useStorybank";
import { useQuery } from "@tanstack/react-query";
import { listOptimizations } from "@/lib/api";
import type { OptimizationSummary } from "@/types";
import { cn } from "@/lib/utils";

const LAST_THREAD_KEY = "coach.lastThreadId";

export default function CoachPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const threadId = searchParams.get("threadId");
  const [activeTab, setActiveTab] = useState<"chat" | "storybank">("chat");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const { data: optimizations = [] } = useQuery<OptimizationSummary[]>({
    queryKey: ["optimizations"],
    queryFn: listOptimizations,
    staleTime: 60_000,
  });
  const { data: sessions = [] } = useCoachSessions();
  const { data: history = [] } = useCoachMessages(threadId);
  const { data: stories = [] } = useStorybank();

  const createThread = useCreateThread();
  const renameThread = useRenameThread();
  const deleteThread = useDeleteThread();

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === threadId) ?? null,
    [sessions, threadId],
  );
  const activeRunId = activeSession?.optimization_run_id ?? null;

  const setActiveThreadId = (id: string | null) => {
    const params = new URLSearchParams(Array.from(searchParams.entries()));
    if (id) params.set("threadId", id);
    else params.delete("threadId");
    router.replace(`/coach${params.toString() ? `?${params.toString()}` : ""}`);
  };

  // Bootstrap from localStorage on first load.
  useEffect(() => {
    if (threadId || sessions.length === 0) return;
    const last = typeof window !== "undefined" ? localStorage.getItem(LAST_THREAD_KEY) : null;
    if (last && sessions.some((s) => s.id === last)) {
      setActiveThreadId(last);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions, threadId]);

  // Persist last viewed thread.
  useEffect(() => {
    if (threadId && typeof window !== "undefined") {
      localStorage.setItem(LAST_THREAD_KEY, threadId);
    }
  }, [threadId]);

  const { streamingMessages, isStreaming, sendMessage } = useCoachChat({
    threadId,
    optimizationRunId: activeRunId,
    onThreadCreated: (newId) => setActiveThreadId(newId),
  });

  const messages = streamingMessages ?? history;

  const existingPositionIds = useMemo(
    () => new Set(sessions.map((s) => s.optimization_run_id)),
    [sessions],
  );

  const handleAddPosition = (runId: string) => {
    createThread.mutate(runId, {
      onSuccess: (created) => setActiveThreadId(created.id),
    });
  };

  const handleNewThreadInPosition = (runId: string) => {
    // If there's already an empty thread in this position, reuse it.
    const empty = sessions.find(
      (s) => s.optimization_run_id === runId && s.message_count === 0,
    );
    if (empty) {
      setActiveThreadId(empty.id);
      return;
    }
    createThread.mutate(runId, {
      onSuccess: (created) => setActiveThreadId(created.id),
    });
  };

  const handleDelete = (id: string) => {
    deleteThread.mutate(id, {
      onSuccess: () => {
        if (id === threadId) {
          // Pick fallback: another thread in same position, else any, else null.
          const sameGroup = sessions.find(
            (s) => s.id !== id && s.optimization_run_id === activeRunId,
          );
          const anyOther = sessions.find((s) => s.id !== id);
          setActiveThreadId((sameGroup ?? anyOther)?.id ?? null);
        }
      },
    });
  };

  const handleSend = (content: string) => {
    if (!threadId && !activeRunId) return;
    sendMessage(content, history);
  };

  const sidebar = (
    <CoachSidebar
      sessions={sessions}
      positions={optimizations}
      activeThreadId={threadId}
      onSelectThread={(id) => {
        setActiveThreadId(id);
        setDrawerOpen(false);
      }}
      onCreateThreadInPosition={handleNewThreadInPosition}
      onAddPosition={() => setPickerOpen(true)}
      onRenameThread={(id, title) => renameThread.mutate({ threadId: id, title })}
      onDeleteThread={handleDelete}
    />
  );

  const headerLabel = activeSession
    ? activeSession.title ?? activeSession.preview ?? "New thread"
    : "Coach";

  return (
    <UpgradeOverlay feature="coach">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mx-auto flex h-[calc(100vh-8rem)] max-w-7xl"
      >
        {/* Web: persistent sidebar */}
        <div className="hidden md:block w-[280px] shrink-0">{sidebar}</div>

        {/* Mobile: drawer */}
        <SidebarDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)}>
          {sidebar}
        </SidebarDrawer>

        <div className="flex flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <button
              type="button"
              className="md:hidden p-1"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open thread list"
            >
              <Menu className="h-5 w-5" />
            </button>
            <span className="flex-1 truncate text-sm font-medium">{headerLabel}</span>
            <div className="flex rounded-lg border border-border bg-muted p-0.5 text-sm shrink-0">
              <button
                className={cn(
                  "rounded-md px-3 py-1 font-medium",
                  activeTab === "chat"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
                onClick={() => setActiveTab("chat")}
              >
                Chat
              </button>
              <button
                className={cn(
                  "rounded-md px-3 py-1 font-medium",
                  activeTab === "storybank"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground",
                )}
                onClick={() => setActiveTab("storybank")}
              >
                Storybank ({stories.length})
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            {activeTab === "chat" ? (
              threadId || activeRunId ? (
                <CoachChat
                  messages={messages}
                  isStreaming={isStreaming}
                  onSend={handleSend}
                />
              ) : (
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  <p className="text-sm">Pick a thread or add a position to start.</p>
                </div>
              )
            ) : (
              <StorybankPanel />
            )}
          </div>
        </div>

        <AddPositionDialog
          open={pickerOpen}
          positions={optimizations}
          existingPositionIds={existingPositionIds}
          onPick={handleAddPosition}
          onClose={() => setPickerOpen(false)}
        />
      </motion.div>
    </UpgradeOverlay>
  );
}
```

**Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

**Step 3: Build**

Run: `cd frontend && npm run build`
Expected: success.

**Step 4: Commit**

```bash
git add frontend/src/app/(protected)/coach/page.tsx
git commit -m "feat(coach): multi-thread sidebar UI on coach page"
```

---

## Phase 7 — Manual e2e + cleanup

### Task 19: Manual e2e checklist

**Step 1: Run backend + frontend**

```bash
./scripts/run-api.sh         # in one terminal
./scripts/run-frontend.sh    # in another
```

**Step 2: Walk the checklist** (each step a separate manual verification)

1. Sign in. Go to `/coach`. With no existing threads, sidebar shows "No threads yet" and "Add position" button.
2. Click "Add position" → picker shows completed optimizations. Pick one → empty thread created and active. URL = `/coach?threadId=<id>`.
3. Send a message. Stream renders. After `done` event, sidebar entry updates with preview text and `last_message_at`.
4. Click "+" next to the same position → second empty thread appears (or focus existing empty one if you didn't send anything yet).
5. Send a different message in the new thread. Switch back to thread #1 by clicking it in sidebar — full history loads.
6. Refresh the browser at `/coach?threadId=<id>` — same thread is active.
7. Open `/coach` (no params) in a new tab — auto-redirects to `?threadId=<lastViewed>` from localStorage.
8. Right-click / kebab → Rename. Type new title, Enter. Sidebar updates.
9. Kebab → Delete on a thread with messages → confirm dialog. Confirm. Thread disappears, falls back to next thread in same group.
10. Resize to mobile width (or DevTools mobile mode). Hamburger appears. Tap it → drawer slides in. Tap thread → drawer closes, chat in focus.

**Step 3: Run all backend tests**

```bash
uv run pytest tests/ -v
```

Expected: all pass.

**Step 4: Frontend lint + build (last gate)**

```bash
cd frontend && npm run lint && npm run build
```

**Step 5: No commit needed unless something was fixed.** If fixes were made, commit them with a descriptive message.

---

### Task 20: Update design doc cross-link (optional polish)

**Files:**
- Modify: `docs/plans/2026-05-03-coach-multi-thread-design.md`

Add a "## Implementation" section at the bottom with a link to this plan. Skip if not desired.

**Commit:**

```bash
git add docs/plans/2026-05-03-coach-multi-thread-design.md
git commit -m "docs: link design to implementation plan"
```

---

## Notes for the executor

- `get_or_create_coach_session` is intentionally removed — search for all call sites with `grep -r "get_or_create_coach_session" src/` and ensure none remain after Phase 2.
- The Telegram bot has a separate Coach handler (`telegram_bot/bot/handlers/coach.py`). Out of scope for this plan; if the bot calls `get_or_create_coach_session`, add a follow-up note but do **not** modify it here unless the test suite breaks.
- The `frontend/src/components/CoachChat.tsx` and `StorybankPanel.tsx` components stay unchanged — they're consumers of the same `CoachMessage[]` shape.
- If the project uses a different dialog primitive (e.g. shadcn Dialog) — replace the inline modal in `AddPositionDialog.tsx` with that component during Task 16.
