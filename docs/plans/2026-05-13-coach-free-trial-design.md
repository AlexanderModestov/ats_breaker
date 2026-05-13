# Coach Free Trial Design

## Overview

Today the Coach feature is locked to `offer_mode` subscribers via a router-level `require_feature(Feature.COACH)` gate in `src/hr_breaker/api/routes/coach.py`. Free and Job Hunter users get zero access — they can't even try it. This design opens a limited trial to non-`offer_mode` users so they can experience Coach before deciding to upgrade.

**The trial:**

| Effective tier | Coach access |
|---|---|
| `offer_mode` | Unlimited (unchanged) |
| `free` **or** `job_hunter` | Lifetime trial: **3 threads × 5 user turns each** |

- Lifetime, not weekly. Once consumed, exhausted forever (until the user upgrades).
- "5 messages" = 5 *user* turns per thread (≤5 assistant replies, ≤10 bubbles total).
- Deleting a thread does **not** refund a slot. Lifetime count is monotonic.
- Job Hunter and Free get the same trial — Job Hunter pays for unlimited Optimize, not for Coach.

**Cap-hit UX:** hard block + the existing `UpgradeOverlay` component (already used elsewhere). No final assistant nudge, no soft inline message.

**Within the 3-thread trial, free users get:** core chat with the coach agent, plus thread rename/delete. They do **not** get Storybank or voice input — those stay `offer_mode`-only and are hidden in the UI.

## Data Model

The lifetime cap needs to survive thread deletion, so `COUNT(*)` over `coach_sessions` is wrong (deleted rows would refund slots). One new column on `profiles`:

```sql
ALTER TABLE profiles
  ADD COLUMN coach_threads_created_total INT NOT NULL DEFAULT 0;
```

Incremented inside `create_coach_session`. Default 0 handles every existing row — no backfill needed. No other schema changes.

Per-thread turn count is derived live from `coach_messages.messages` (count of `UserPromptPart` entries). Free Coach threads are tiny by design (≤10 bubbles), so live counting is cheap.

## Backend

### Feature matrix change

In `src/hr_breaker/services/tiers.py`:

```python
FEATURE_MIN_TIER[Feature.COACH] = "free"   # was "offer_mode"

FREE_COACH_THREADS = 3
FREE_COACH_TURNS   = 5

def coach_is_unlimited(profile: dict) -> bool:
    return effective_tier(profile) == "offer_mode"
```

The router-level `require_feature(Feature.COACH)` at `src/hr_breaker/api/routes/coach.py:26` stays — it now passes every signed-in user. **Quota is the real gate**, enforced per-endpoint.

### Endpoint-level checks

| Endpoint | Check |
|---|---|
| `POST /coach/sessions` (create thread) | If not unlimited and `coach_threads_created_total >= 3` → 403 `{code: "coach_thread_limit"}`. |
| `POST /coach/chat` with `thread_id` | If not unlimited and the thread already has ≥5 `UserPromptPart`s → 403 `{code: "coach_turn_limit"}`. |
| `POST /coach/chat` with `optimization_run_id` (lazy create) | Apply thread-cap check before creating. New thread has 0 turns so turn cap is trivially fine. |
| `GET /coach/sessions`, `GET /sessions/{id}/messages`, `PATCH /sessions/{id}`, `DELETE /sessions/{id}` | **No quota check.** A trial user with 3 used threads can still browse, rename, and delete. |

### Supabase service

One new helper in `src/hr_breaker/services/supabase.py`:

```python
def count_coach_sessions(user_id: str) -> int:
    """Lifetime count of threads ever created (reads coach_threads_created_total)."""
```

`create_coach_session` is modified to atomically increment `coach_threads_created_total` in the same transaction as inserting the row.

### Agent

**No changes.** The coach agent in `src/hr_breaker/agents/coach.py` has zero tools — only a system prompt + dynamic context. "No Storybank for free users" is a pure frontend concern (the agent doesn't write to `storybank_entries`).

### Telemetry

Structured backend logs on cap hits:
- `coach_thread_limit_hit` — user, threads_total_at_block
- `coach_turn_limit_hit` — user, thread_id, turns_at_block

Frontend re-emits the same on 403 via the existing PostHog wrapper.

## Frontend

### Quota in the subscription payload

Extend `GET /api/subscription`'s `SubscriptionStatusResponse` with a `coach` block. Single source of truth, already cached by `useSubscription`:

```ts
coach: {
  is_unlimited: boolean;
  threads_remaining: number;   // 0..3 for trial, ignored if is_unlimited
  threads_total: 3;            // constant for trial, for display
}
```

Per-thread turn count remains computed client-side from loaded messages.

### Gating in components

**`CoachSidebar` — "New thread" button:**
- Disabled when `threads_remaining === 0 && !is_unlimited`.
- Click opens `UpgradeOverlay` with copy key `coach.cap.threads`.
- Shows live chip *"X of 3 dialogs left"* for trial users (visible scarcity).

**`CoachChat` — input + send:**
- After each assistant stream completes, recount user turns in the active thread.
- When `userTurns >= 5 && !is_unlimited`, disable the textarea + send and render `UpgradeOverlay` inline above the input with copy key `coach.cap.turns`.
- No toast — the overlay is the conversion moment.

**`useCoach` — 403 fallback:**
- Even with proactive disabling, the chat mutation must handle 403 `{code: "coach_thread_limit" | "coach_turn_limit"}` (race conditions, tab desync) by opening the matching overlay.

### Page-level zero states on `/coach`

Four states matter for trial users:

| State | Trigger | UI |
|---|---|---|
| A — No positions yet | `optimizations.length === 0` | Centered card: "Coach helps you practice for a specific job. Optimize your CV against a job posting first." Primary CTA → `/optimize`. Trial banner: *"You'll get 3 free Coach dialogs, 5 messages each."* |
| B — 0 threads created | `sessions.length === 0`, `threads_remaining === 3` | Standard CoachChat empty state + soft chip *"3 free dialogs available."* |
| C — Mid-trial | `0 < threads_remaining < 3` | Sidebar as today. "New thread" enabled with live chip. |
| D — Cap reached | `threads_remaining === 0` | "New thread" disabled with lock icon → overlay on click. Existing threads remain fully browsable/renameable/deletable. One-line note under sidebar header: *"Deleting a dialog won't free up a slot."* — avoids the obvious footgun. |

### Pricing page (`/pricing`)

On the **Free** and **Job Hunter** plan cards: Coach line changes from "—" to *"Coach trial: 3 dialogs × 5 messages."* Offer Mode card: *"Coach: unlimited."* No CTA logic changes.

### Translations

Two new keys in `frontend/src/app/_lib/translations.ts`, EN + RU:
- `coach.cap.threads` — thread cap overlay copy.
- `coach.cap.turns` — turn cap overlay copy.

## Testing

### Backend (pytest)

- `coach_is_unlimited` returns true only for `offer_mode`.
- Free user: 3 thread creates succeed, 4th → 403 `coach_thread_limit`.
- Free user in one thread: 5 turns succeed, 6th → 403 `coach_turn_limit`.
- **No-refund test:** create thread, delete it, try to create another → still 403. Locks in counter behavior.
- Job Hunter user hits the same 403s (parity with free).
- Offer Mode user: 4th thread, 6th turn → both 200.
- After cap, `list_sessions` / `get_messages` / `rename` / `delete` all 200.
- Migration idempotency: re-running adds nothing.

### Frontend

Smoke tests on the disabled-button + overlay flow in `CoachSidebar` and `CoachChat`. Mock a 403 in `useCoach` and assert the right overlay opens — that's the critical resilience path.

## Rollout

No feature flag. The change is strictly looser than today (free / job_hunter went from "no access" to "limited access"). Nothing regresses for `offer_mode` users.

Deploy order:
1. **Migration** — add `coach_threads_created_total`.
2. **Backend** — feature gate lowered, endpoint checks, increment-on-create, telemetry, `coach` field added to subscription response.
3. **Frontend** — consume `coach` block, sidebar/chat gates, pricing copy, translations.

If step 2 ships before 3, free users can technically hit Coach via direct API call but the UI shows nothing new — harmless. Reverse order would show counters reading from a missing field — keep the stated order.

## Monitoring

Watch `coach_thread_limit_hit` and `coach_turn_limit_hit` event counts vs. upgrade-clicks originating from the Coach overlay. That's the conversion funnel for this feature. Expected outcome over the first 30 days: a non-trivial share of free users who finish their 3rd thread or 5th turn click through to Offer Mode upgrade.

## Out of scope (YAGNI)

- **Weekly reset.** Lifetime cap is final — chose explicitly during brainstorming.
- **Refund on delete.** Strict no-refund — locks in conversion pressure.
- **Different model/prompt for trial.** Same Gemini call, same `coach_system.md` — no tier-aware prompt branching.
- **Anonymous trial.** Sign-in still required.
- **Storybank for free / voice input for free.** Both stay `offer_mode`-only.
- **Server-side rate limiting beyond the caps.** The caps are the limit.
- **State D header chip.** Disabled button + overlay communicate cap-reached clearly enough — adding a chip on top would be redundant. Easy to revisit later if conversion data suggests it.
