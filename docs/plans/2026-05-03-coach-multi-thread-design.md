# Coach Multi-Thread — Design Document

## Goals

1. Load full message history when a user returns to a previously used position.
2. Support multiple threads per position so users can discuss a position from different angles.

The current implementation has `UNIQUE(user_id, optimization_run_id)` on `coach_sessions` and resets `sessionId` to `null` on position change, which prevents history from loading until the user sends a new message.

## Data Model

New migration `supabase/migrations/015_coach_threads.sql`:

```sql
ALTER TABLE coach_sessions
    DROP CONSTRAINT coach_sessions_user_id_optimization_run_id_key;

ALTER TABLE coach_sessions ADD COLUMN title VARCHAR(255);
ALTER TABLE coach_sessions ADD COLUMN last_message_at TIMESTAMPTZ;

UPDATE coach_sessions SET last_message_at = updated_at WHERE last_message_at IS NULL;

CREATE INDEX idx_coach_sessions_user_run
    ON coach_sessions(user_id, optimization_run_id, last_message_at DESC);
```

`coach_messages` and `storybank_entries` are unchanged.

`title` semantics:
- `NULL` + has messages → frontend shows preview of first user message (~40 chars).
- `NULL` + no messages (lazy-created) → frontend shows "New thread".
- non-`NULL` → manual rename.

Existing rows become "first thread" of their position automatically. No data migration needed beyond the backfill above.

## Backend API

In code we keep `session_id`; in URLs and frontend types we expose `thread_id` (renaming only).

### Changed endpoints (`src/hr_breaker/api/routes/coach.py`)

| Method | Path | Change |
|--------|------|--------|
| `GET` | `/api/coach/sessions` | Returns `id, optimization_run_id, title, last_message_at, message_count, preview`. |
| `POST` | `/api/coach/chat` | Accepts either `thread_id` (existing thread) or `optimization_run_id` (lazy-create). Exactly one must be provided. Removes `get_or_create_coach_session`. |
| `GET` | `/api/coach/sessions/{id}/messages` | Unchanged. |

### New endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/coach/sessions` | Body `{ optimization_run_id }`. Creates an empty thread (used by "+ Add position" flow). |
| `PATCH` | `/api/coach/sessions/{id}` | Body `{ title }`. Rename. |
| `DELETE` | `/api/coach/sessions/{id}` | Deletes thread (cascade removes messages). |

### Lazy creation in `/chat`

If only `optimization_run_id` is provided, the chat handler creates the `coach_sessions` row internally and returns the new `thread_id` in the SSE `done` event. The frontend updates the URL to `?threadId=<new>`.

### Schemas

`CoachChatRequest`:
- `optimization_run_id: Optional[UUID]`
- `thread_id: Optional[UUID]`
- validator: exactly one is set.

`CoachSessionResponse` adds: `title`, `last_message_at`, `message_count`, `preview`.

## Frontend — Sidebar / Drawer

### Layout

**Web (≥768px):** persistent left sidebar 280px + chat area. The existing top `<select>` for position is removed — its role is taken by the sidebar.

**Mobile (<768px):** sidebar collapses into a drawer. Hamburger icon in the chat header opens it (85% width + backdrop). Tapping a thread closes the drawer.

### Sidebar contents

```
┌─────────────────────────────┐
│ 🔍 Search threads           │
├─────────────────────────────┤
│ + Add position              │
├─────────────────────────────┤
│ ▼ Acme Corp — Senior PM  +  │
│    • STAR ответ про конф... │  <- active (highlighted)
│    • Разбор тех. секции     │
│    • Conversation 1         │
│ ▼ Stripe — Eng Manager   +  │
│    • New thread             │
│ ▶ Notion — PM            +  │
└─────────────────────────────┘
```

- Groups by `optimization_run_id`. Header = `job_company — job_title`.
- Only positions with ≥1 thread are shown (plus the active thread's position).
- "+" inside a group creates a new thread for that position.
- "+ Add position" opens a picker over all `optimizations` (reuses the data already fetched on the page) and creates an empty thread there.
- Threads sorted by `last_message_at DESC`; nulls (empty) first.
- Hover/long-press → kebab menu → Rename / Delete.
- Rename = inline edit (input replaces title; Enter saves).
- Delete confirms only if `message_count > 0`.

### New components

- `frontend/src/components/coach/CoachSidebar.tsx`
- `frontend/src/components/coach/ThreadListItem.tsx`
- `frontend/src/components/coach/AddPositionDialog.tsx`
- `frontend/src/components/coach/SidebarDrawer.tsx`

## Frontend — State, Hooks, Routing

`activeThreadId` is derived from `useSearchParams().get("threadId")`. No local `useState` for it — eliminates the current bootstrap race in `useCoachChat`.

### Hooks (`frontend/src/hooks/useCoach.ts`)

```ts
useCoachSessions()                        // ['coach-sessions'] — sidebar source
useCoachMessages(threadId: string|null)   // ['coach-messages', threadId]
useCoachChat()                            // simplified: no internal sessionId
                                          // sendMessage(threadId|null, runId, content)
                                          // on done → router.replace(?threadId=...)

useCreateThread()  // POST /api/coach/sessions, optimistic add
useRenameThread()  // PATCH, optimistic
useDeleteThread()  // DELETE, then redirect to fallback thread or /coach
```

### Bootstrap

```ts
const threadId = searchParams.get("threadId");
const { data: sessions = [] } = useCoachSessions();
const { data: messages = [] } = useCoachMessages(threadId);

useEffect(() => {
  if (threadId || sessions.length === 0) return;
  const last = localStorage.getItem("coach.lastThreadId");
  if (last && sessions.some(s => s.id === last)) {
    router.replace(`/coach?threadId=${last}`);
  }
}, [threadId, sessions]);

useEffect(() => {
  if (threadId) localStorage.setItem("coach.lastThreadId", threadId);
}, [threadId]);
```

### Sidebar grouping

Pure frontend `useMemo` over `sessions`, grouped by `optimization_run_id`, threads sorted by `last_message_at DESC` with nulls first.

### Cache invalidation

- SSE `done` → invalidate `['coach-sessions']` to refresh preview / `last_message_at`.
- Rename / delete → optimistic update, then invalidate.

## Edge Cases

- **Deleting the active thread:** pick next thread in the same group (by `last_message_at DESC`); if none, next thread anywhere; if none at all, `router.replace('/coach')` and show empty state.
- **Position deleted:** existing `ON DELETE CASCADE` removes sessions; sidebar drops the group on next invalidate.
- **Empty lazy thread + repeat "+":** if a position already has a thread with `message_count === 0`, focus it instead of creating a duplicate.
- **Streaming + thread switch:** `useCoachChat` keeps `inFlightThreadId`; SSE deltas update `messages` only if it equals `activeThreadId`. The stream completes server-side either way.
- **Rename conflict / failure:** optimistic update with rollback + toast.

## Testing

### Backend (`tests/api/test_coach_routes.py`)

- `POST /chat` without `thread_id` creates a new thread and returns it in `done`.
- `POST /chat` with `thread_id` appends to history and reloads `message_history` correctly.
- Validator rejects both / neither of `thread_id` and `optimization_run_id`.
- `PATCH /sessions/{id}` updates title; cross-user request returns 404.
- `DELETE /sessions/{id}` cascades to messages; cross-user returns 404.
- `GET /sessions` returns correct `preview` and `message_count`.

### Frontend (vitest)

- `useCoachChat` streams into the active thread; switching mid-stream does not leak deltas into the new one.
- Sidebar grouping and sort order.
- Bootstrap from `localStorage` and fallback to empty state.

### Manual / e2e checklist

- Create thread → send message → switch position → return → history visible.
- Create a second thread in the same position → conversations stay independent.
- Refresh `/coach?threadId=xxx` preserves the thread.
- Mobile drawer opens/closes; hardware back navigates.
