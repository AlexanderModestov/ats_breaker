# Coach Free Trial Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Open the Coach feature to `free` and `job_hunter` users as a lifetime trial: 3 threads × 5 user turns each, hard-blocked with `UpgradeOverlay` on cap.

**Architecture:** One new column on `profiles` (`coach_threads_created_total`) to track lifetime thread creation (so deletes don't refund slots). Lower `FEATURE_MIN_TIER[Feature.COACH]` to `"free"` so the router gate passes everyone signed-in; enforce quota per-endpoint instead. Per-thread turn cap is derived live from `coach_messages.messages` (count of `UserPromptPart`). Frontend reads quota from an expanded `/api/subscription` response.

**Tech Stack:** FastAPI + Pydantic backend, Supabase (Postgres) for persistence, Next.js 14 + React Query frontend, pytest for backend tests. No frontend test framework installed — frontend tasks include a manual smoke checklist instead of automated tests.

**Design doc:** `docs/plans/2026-05-13-coach-free-trial-design.md`.

**Worktree:** `.worktrees/coach-free-trial` on branch `feature/coach-free-trial`.

**Setup before first task:**
```bash
uv sync
cd frontend && npm install && cd ..
```

---

## Task 1: Migration — add `coach_threads_created_total` column

**Files:**
- Create: `supabase/migrations/017_coach_trial_counter.sql`

**Step 1: Write the migration**

```sql
-- 017_coach_trial_counter.sql — lifetime thread counter for the Coach free trial.
-- Source of truth for the "3 dialogs ever" cap on free / job_hunter tiers.
-- Counts threads ever created (not currently present) so deletes don't refund slots.
-- Idempotent: safe to re-run.

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS coach_threads_created_total INT NOT NULL DEFAULT 0;
```

**Step 2: Apply locally**

Run: `supabase db reset` (or whichever command this project uses against the local Supabase) — verify migration applies clean.
Expected: column visible in `profiles` schema, default 0.

**Step 3: Commit**

```bash
git add supabase/migrations/017_coach_trial_counter.sql
git commit -m "feat(db): add coach_threads_created_total counter on profiles"
```

---

## Task 2: tiers.py — constants and `coach_is_unlimited` helper

**Files:**
- Modify: `src/hr_breaker/services/tiers.py`
- Test: `tests/test_tiers.py`

**Step 1: Write the failing test**

Append to `tests/test_tiers.py`:

```python
from hr_breaker.services.tiers import (
    FREE_COACH_THREADS,
    FREE_COACH_TURNS,
    coach_is_unlimited,
)


class TestCoachTrialConstants:
    def test_thread_limit_is_3(self):
        assert FREE_COACH_THREADS == 3

    def test_turn_limit_is_5(self):
        assert FREE_COACH_TURNS == 5


class TestCoachIsUnlimited:
    def test_free_is_not_unlimited(self):
        assert coach_is_unlimited(_profile()) is False

    def test_job_hunter_is_not_unlimited(self):
        p = _profile(subscription_tier="job_hunter", subscription_status="active")
        assert coach_is_unlimited(p) is False

    def test_offer_mode_active_is_unlimited(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_is_unlimited(p) is True

    def test_offer_mode_cancelled_within_grace_is_unlimited(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=future,
        )
        assert coach_is_unlimited(p) is True

    def test_offer_mode_cancelled_after_grace_is_not_unlimited(self):
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        p = _profile(
            subscription_tier="offer_mode",
            subscription_status="cancelled",
            current_period_end=past,
        )
        assert coach_is_unlimited(p) is False
```

**Step 2: Run test, verify it fails**

Run: `uv run pytest tests/test_tiers.py::TestCoachTrialConstants -v tests/test_tiers.py::TestCoachIsUnlimited -v`
Expected: ImportError / AttributeError for missing names.

**Step 3: Implement minimal code**

In `src/hr_breaker/services/tiers.py`, after `FREE_WEEKLY_LIMIT`:

```python
FREE_COACH_THREADS = 3
FREE_COACH_TURNS = 5


def coach_is_unlimited(profile: dict) -> bool:
    """True when the user has unlimited Coach access (Offer Mode, including cancellation grace)."""
    return effective_tier(profile) == "offer_mode"
```

**Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: all green.

**Step 5: Commit**

```bash
git add src/hr_breaker/services/tiers.py tests/test_tiers.py
git commit -m "feat(tiers): coach trial constants and coach_is_unlimited helper"
```

---

## Task 3: Lower `FEATURE_MIN_TIER[Feature.COACH]` to `"free"`

**Files:**
- Modify: `src/hr_breaker/services/tiers.py:18` (the FEATURE_MIN_TIER dict)
- Modify: `tests/test_tiers.py` (update `test_coach_requires_offer_mode`)

**Step 1: Update the existing test to reflect the new gate**

In `tests/test_tiers.py`, find `test_coach_requires_offer_mode` (around line 39) and replace it:

```python
def test_coach_open_to_free_for_trial(self):
    # Tier gate passes everyone signed-in; quota check enforces the trial caps.
    # See FREE_COACH_THREADS / FREE_COACH_TURNS.
    assert FEATURE_MIN_TIER[Feature.COACH] == "free"
```

**Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_tiers.py::TestFeatureMatrix -v`
Expected: assertion fails — current value is `"offer_mode"`.

**Step 3: Flip the matrix value**

In `src/hr_breaker/services/tiers.py`:

```python
FEATURE_MIN_TIER: dict[Feature, str] = {
    Feature.OPTIMIZE: "free",
    Feature.COACH: "free",  # was "offer_mode" — quota gates the trial now
    Feature.COVER_LETTER: "offer_mode",
    Feature.GAP_ANALYSIS: "offer_mode",
}
```

**Step 4: Run all tier + require_feature tests**

Run: `uv run pytest tests/test_tiers.py tests/test_require_feature.py -v`
Expected: all green. If `test_require_feature.py` has a test that asserts free is blocked from coach, update it to expect access — the comment in the new test explains why.

**Step 5: Commit**

```bash
git add src/hr_breaker/services/tiers.py tests/test_tiers.py tests/test_require_feature.py
git commit -m "feat(tiers): lower coach feature gate to free; quota gates the trial"
```

---

## Task 4: Supabase service — increment counter in `create_coach_session`

**Files:**
- Modify: `src/hr_breaker/services/supabase.py:348-368`
- Test: `tests/test_coach_routes.py` (already exists; add a new test class)

**Note:** `create_coach_session` is called via the supabase service, which is mocked in route tests. We test the increment behavior via a unit test that asserts the supabase client's `.rpc` (or `.update`) was called with the right args.

**Step 1: Write the failing test**

Add to `tests/test_coach_routes.py`:

```python
class TestCreateCoachSessionIncrementsCounter:
    """Verify the counter is incremented atomically when a thread is created."""

    def test_increment_called_on_create(self, monkeypatch):
        from hr_breaker.services.supabase import SupabaseService

        captured_rpc = []

        class FakeBuilder:
            def insert(self, _payload): return self
            def execute(self):
                return MagicMock(data=[{"id": "s1", "user_id": USER, "optimization_run_id": "r1"}])

        class FakeClient:
            def table(self, _name): return FakeBuilder()
            def rpc(self, fn, params):
                captured_rpc.append((fn, params))
                return MagicMock(execute=lambda: MagicMock(data=None))

        svc = SupabaseService.__new__(SupabaseService)
        svc._client = FakeClient()
        svc.create_coach_session(USER, "r1")

        assert captured_rpc == [("increment_coach_threads_created_total", {"p_user_id": USER})]
```

**Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_coach_routes.py::TestCreateCoachSessionIncrementsCounter -v`
Expected: assertion fails — RPC not called yet.

**Step 3: Add the Postgres RPC for the atomic increment**

Append to `supabase/migrations/017_coach_trial_counter.sql`:

```sql
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
```

Re-apply the migration locally.

**Step 4: Implement the increment in `create_coach_session`**

In `src/hr_breaker/services/supabase.py`, modify `create_coach_session`:

```python
def create_coach_session(
    self,
    user_id: str,
    optimization_run_id: str,
) -> dict[str, Any]:
    """Create a new coach session (thread) and bump the lifetime counter."""
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
        self._client.rpc(
            "increment_coach_threads_created_total",
            {"p_user_id": user_id},
        ).execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Failed to create coach session: {e}")
        raise SupabaseError(f"Failed to create coach session: {e}") from e
```

**Step 5: Verify**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: all green, including the new test.

**Step 6: Commit**

```bash
git add supabase/migrations/017_coach_trial_counter.sql src/hr_breaker/services/supabase.py tests/test_coach_routes.py
git commit -m "feat(coach): bump coach_threads_created_total atomically on create"
```

---

## Task 5: Endpoint — thread cap on `POST /coach/sessions`

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py:83-94`
- Test: `tests/test_coach_routes.py`

**Step 1: Write failing tests**

Add to `tests/test_coach_routes.py`:

```python
def _free_profile() -> dict:
    return {
        "id": USER,
        "subscription_tier": "free",
        "subscription_status": "none",
        "current_period_end": None,
        "period_request_count": 0,
        "weekly_reset_at": "2099-01-01T00:00:00+00:00",
        "coach_threads_created_total": 0,
    }


class TestCoachThreadCap:
    def test_free_user_under_cap_can_create(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 2}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "new", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-05-14T00:00:00Z",
            "updated_at": "2026-05-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201

    def test_free_user_at_cap_is_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 3}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"

    def test_job_hunter_at_cap_is_blocked(self, client, fake_supabase):
        p = _free_profile()
        p.update(subscription_tier="job_hunter", subscription_status="active", coach_threads_created_total=3)
        fake_supabase.get_profile.return_value = p
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"

    def test_offer_mode_past_cap_can_create(self, client, fake_supabase):
        # Already at 999 (impossible for trial) — unlimited tier ignores the counter.
        p = {**_offer_mode_profile(), "coach_threads_created_total": 999}
        fake_supabase.get_profile.return_value = p
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "new", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-05-14T00:00:00Z",
            "updated_at": "2026-05-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201
```

**Step 2: Run, verify they fail**

Run: `uv run pytest tests/test_coach_routes.py::TestCoachThreadCap -v`
Expected: tests fail — endpoint doesn't enforce the cap yet.

**Step 3: Implement the check**

In `src/hr_breaker/api/routes/coach.py`, top of file:

```python
from hr_breaker.services.tiers import (
    Feature,
    FREE_COACH_THREADS,
    coach_is_unlimited,
)
```

Modify `create_thread`:

```python
@router.post("/sessions", response_model=CoachSessionResponse, status_code=201)
async def create_thread(
    body: CoachThreadCreateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Create an empty coach thread for a position."""
    profile = supabase.get_profile(user_id) or {}
    if not coach_is_unlimited(profile):
        used = profile.get("coach_threads_created_total", 0)
        if used >= FREE_COACH_THREADS:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "coach_thread_limit",
                    "message": "You've used all 3 free Coach dialogs. Upgrade to Offer Mode to keep going.",
                },
            )

    run = supabase.get_optimization_run(body.optimization_run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")
    session = supabase.create_coach_session(user_id, body.optimization_run_id)
    return {**session, "preview": None, "message_count": 0}
```

**Step 4: Run all coach route tests, verify green**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: all green.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py tests/test_coach_routes.py
git commit -m "feat(coach): thread cap of 3 on POST /coach/sessions for trial users"
```

---

## Task 6: Endpoint — thread cap on `POST /coach/chat` (lazy-create path)

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py:124-148` (the lazy-create branch of `chat`)
- Test: `tests/test_coach_routes.py`

**Step 1: Write the failing test**

Add to `tests/test_coach_routes.py`:

```python
class TestCoachChatLazyCreateCap:
    def test_free_user_at_cap_blocked_on_lazy_chat(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 3}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post("/api/coach/chat", json={"optimization_run_id": "r1", "message": "hi"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_thread_limit"
```

**Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_coach_routes.py::TestCoachChatLazyCreateCap -v`
Expected: fails (returns 200 or streams successfully).

**Step 3: Implement the check at the top of the lazy-create branch**

In `src/hr_breaker/api/routes/coach.py`, inside `chat`, before the lazy-create call:

```python
    # Resolve thread.
    if body.thread_id:
        session = supabase.get_coach_session(body.thread_id, user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Thread not found")
        optimization_run_id = session["optimization_run_id"]
    else:
        # Lazy create path — enforce the trial thread cap before creating.
        profile = supabase.get_profile(user_id) or {}
        if not coach_is_unlimited(profile):
            used = profile.get("coach_threads_created_total", 0)
            if used >= FREE_COACH_THREADS:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "coach_thread_limit",
                        "message": "You've used all 3 free Coach dialogs. Upgrade to Offer Mode to keep going.",
                    },
                )
        check_run = supabase.get_optimization_run(body.optimization_run_id, user_id)
        if not check_run:
            raise HTTPException(status_code=404, detail="Optimization run not found")
        session = supabase.create_coach_session(user_id, body.optimization_run_id)
        optimization_run_id = body.optimization_run_id
```

**Step 4: Verify**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py tests/test_coach_routes.py
git commit -m "feat(coach): enforce thread cap on lazy-create chat path"
```

---

## Task 7: Endpoint — turn cap on `POST /coach/chat` (existing thread)

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py:124-218` (the `chat` function)
- Test: `tests/test_coach_routes.py`

**Step 1: Write the failing test**

Add to `tests/test_coach_routes.py`:

```python
class TestCoachChatTurnCap:
    @staticmethod
    def _history_with_user_turns(n: int) -> list[dict]:
        # Minimal Pydantic-AI message format with `n` UserPromptParts.
        msgs = []
        for i in range(n):
            msgs.append({
                "kind": "request",
                "parts": [{"part_kind": "user-prompt", "content": f"q{i}"}],
            })
            msgs.append({
                "kind": "response",
                "parts": [{"part_kind": "text", "content": f"a{i}"}],
            })
        return msgs

    def test_free_user_under_turn_cap_passes(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 1}
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        fake_supabase.get_coach_messages.return_value = self._history_with_user_turns(4)
        # Don't fully stream — just assert the cap check passes (200 stream start).
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200

    def test_free_user_at_turn_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 1}
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_coach_messages.return_value = self._history_with_user_turns(5)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "coach_turn_limit"

    def test_offer_mode_past_turn_cap_passes(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _offer_mode_profile()
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        fake_supabase.get_coach_messages.return_value = self._history_with_user_turns(50)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200
```

**Step 2: Run, verify failures**

Run: `uv run pytest tests/test_coach_routes.py::TestCoachChatTurnCap -v`
Expected: `test_free_user_at_turn_cap_blocked` fails.

**Step 3: Implement the check**

In `src/hr_breaker/api/routes/coach.py`, after the existing `if body.thread_id:` resolution block, before loading optimization run:

```python
    # Enforce trial turn cap for non-unlimited users on existing threads.
    if body.thread_id:
        profile = supabase.get_profile(user_id) or {}
        if not coach_is_unlimited(profile):
            raw_history = supabase.get_coach_messages(session["id"])
            user_turns = sum(
                1
                for msg in raw_history
                if msg.get("kind") == "request"
                for part in msg.get("parts", [])
                if part.get("part_kind") == "user-prompt"
            )
            if user_turns >= FREE_COACH_TURNS:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "coach_turn_limit",
                        "message": "This dialog has reached the 5-message limit. Start a new dialog or upgrade.",
                    },
                )
```

Add `FREE_COACH_TURNS` to the import at the top.

**Note:** This re-loads `coach_messages` once for the cap check, then again later in the streaming setup. Acceptable cost (single SELECT). Refactoring to share the load is YAGNI — flagged but not addressed.

**Step 4: Verify**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py tests/test_coach_routes.py
git commit -m "feat(coach): turn cap of 5 on POST /coach/chat for trial users"
```

---

## Task 8: Subscription endpoint — add `coach` block

**Files:**
- Modify: `src/hr_breaker/api/routes/subscription.py:31-60`
- Test: `tests/test_access_control.py` or create `tests/test_subscription_routes.py`

**Step 1: Decide test location**

Check if `tests/test_access_control.py` already covers `GET /api/subscription`. If yes, add tests there; if no, create `tests/test_subscription_routes.py` mirroring the `client` fixture pattern from `test_coach_routes.py`.

**Step 2: Write the failing test**

```python
class TestSubscriptionCoachBlock:
    def test_free_user_response_includes_coach_block(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 1}
        r = client.get("/api/subscription")
        assert r.status_code == 200
        body = r.json()
        assert body["coach"] == {
            "is_unlimited": False,
            "threads_remaining": 2,
            "threads_total": 3,
        }

    def test_offer_mode_user_coach_block_is_unlimited(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_offer_mode_profile(), "coach_threads_created_total": 99}
        r = client.get("/api/subscription")
        body = r.json()
        assert body["coach"]["is_unlimited"] is True
        assert body["coach"]["threads_remaining"] == 0  # ignored when unlimited; surface 0 for type stability

    def test_free_user_at_cap_remaining_is_zero(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {**_free_profile(), "coach_threads_created_total": 5}
        r = client.get("/api/subscription")
        assert r.json()["coach"]["threads_remaining"] == 0  # clamped, never negative
```

**Step 3: Run, verify failures**

Run: `uv run pytest tests/test_subscription_routes.py -v` (or wherever placed)
Expected: KeyError on `body["coach"]`.

**Step 4: Implement**

In `src/hr_breaker/api/routes/subscription.py`:

```python
from hr_breaker.services.tiers import (
    FREE_COACH_THREADS,
    coach_is_unlimited,
    effective_tier,
)


class CoachAccessBlock(BaseModel):
    is_unlimited: bool
    threads_remaining: int
    threads_total: int


class SubscriptionStatusResponse(BaseModel):
    tier: str
    status: str
    remaining: int | None
    is_unlimited: bool
    weekly_reset_at: str | None
    current_period_end: str | None
    coach: CoachAccessBlock
```

In `get_subscription_status`:

```python
    unlimited = coach_is_unlimited(profile)
    used = profile.get("coach_threads_created_total", 0)
    threads_remaining = 0 if unlimited else max(0, FREE_COACH_THREADS - used)

    return SubscriptionStatusResponse(
        tier=effective_tier(profile),
        status=profile.get("subscription_status", "none"),
        remaining=None if quota.unlimited else quota.remaining,
        is_unlimited=quota.unlimited,
        weekly_reset_at=profile.get("weekly_reset_at"),
        current_period_end=profile.get("current_period_end"),
        coach=CoachAccessBlock(
            is_unlimited=unlimited,
            threads_remaining=threads_remaining,
            threads_total=FREE_COACH_THREADS,
        ),
    )
```

**Step 5: Verify**

Run: `uv run pytest tests/ -v -k subscription`
Expected: green.

**Step 6: Commit**

```bash
git add src/hr_breaker/api/routes/subscription.py tests/test_subscription_routes.py
git commit -m "feat(api): expose coach trial quota in /api/subscription"
```

---

## Task 9: Frontend types — extend `SubscriptionStatus`

**Files:**
- Modify: `frontend/src/types/index.ts` (or wherever `SubscriptionStatus` is defined — find via grep)

**Step 1: Locate the type**

Run: `grep -rn "is_unlimited" frontend/src --include="*.ts" --include="*.tsx" | head -5`

**Step 2: Extend the type**

Add to `SubscriptionStatus`:

```ts
coach: {
  is_unlimited: boolean;
  threads_remaining: number;
  threads_total: number;
};
```

**Step 3: TypeScript build check**

Run: `cd frontend && npx tsc --noEmit`
Expected: any consumer that destructures `SubscriptionStatus` without `coach` either still compiles (optional access) or surfaces a real callsite to fix. Fix only the callsites broken by this change — don't refactor adjacent code.

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add coach quota block to SubscriptionStatus type"
```

---

## Task 10: Frontend — `CoachSidebar` thread-cap gate

**Files:**
- Modify: `frontend/src/components/coach/CoachSidebar.tsx`
- Modify (if needed): `frontend/src/components/UpgradeOverlay.tsx` (only if a new copy variant is required)

**Step 1: Read current sidebar to find the "New thread" CTA**

Run: `grep -n "New thread\|new.*thread\|createThread\|onCreate" frontend/src/components/coach/CoachSidebar.tsx`

**Step 2: Implement gate**

Inside `CoachSidebar`:

```tsx
import { useSubscription } from "@/hooks/useSubscription";
import { useTranslation } from "@/app/_lib/translations";

const { data: sub } = useSubscription();
const t = useTranslation();

const isTrialUser = sub && !sub.coach.is_unlimited;
const threadsRemaining = sub?.coach.threads_remaining ?? 0;
const atThreadCap = isTrialUser && threadsRemaining <= 0;

const [overlayOpen, setOverlayOpen] = useState(false);

const handleNewThread = () => {
  if (atThreadCap) {
    setOverlayOpen(true);
    return;
  }
  onCreateThread(); // existing handler
};
```

Render:

```tsx
<Button onClick={handleNewThread} disabled={false /* keep enabled so click opens overlay */}>
  {atThreadCap && <LockIcon className="mr-2 h-4 w-4" />}
  New thread
</Button>

{isTrialUser && (
  <p className="px-3 py-1 text-xs text-muted-foreground">
    {t("coach.trial.threads_chip", { remaining: threadsRemaining, total: 3 })}
  </p>
)}

{atThreadCap && (
  <p className="px-3 pb-2 text-xs text-muted-foreground">
    {t("coach.trial.delete_no_refund")}
  </p>
)}

<UpgradeOverlay
  open={overlayOpen}
  onClose={() => setOverlayOpen(false)}
  copyKey="coach.cap.threads"
/>
```

**Note:** the existing `UpgradeOverlay` API may or may not accept a `copyKey` prop. Inspect the component before adding the prop — if it currently takes a single hardcoded message, the smallest viable change is adding an optional prop that selects between the existing message and the new one. Do not redesign the component.

**Step 3: Manual smoke check**

1. Start backend + frontend: `uv run uvicorn hr_breaker.api.main:app --reload` and `cd frontend && npm run dev`.
2. Log in as a free user with `coach_threads_created_total = 2` in Supabase.
3. Visit `/coach`. Sidebar should show *"1 of 3 dialogs left"*. "New thread" creates one.
4. Refresh. Counter should read *"0 of 3 dialogs left"*. "New thread" button shows lock icon and opens overlay on click.
5. Switch user to `offer_mode`. No chip, no lock icon, unlimited.

**Step 4: Commit**

```bash
git add frontend/src/components/coach/CoachSidebar.tsx frontend/src/components/UpgradeOverlay.tsx
git commit -m "feat(frontend): coach sidebar thread-cap gate + scarcity chip"
```

---

## Task 11: Frontend — `CoachChat` turn-cap gate

**Files:**
- Modify: `frontend/src/components/CoachChat.tsx`

**Step 1: Locate the chat input + message list**

Run: `grep -n "textarea\|send\|onSubmit\|messages" frontend/src/components/CoachChat.tsx | head -20`

**Step 2: Implement gate**

```tsx
const { data: sub } = useSubscription();
const isTrialUser = sub && !sub.coach.is_unlimited;

// Count user turns in current thread.
const userTurns = messages.filter(m => m.role === "user").length;
const atTurnCap = isTrialUser && userTurns >= 5;

// Disable input + show inline overlay when capped.
<textarea disabled={atTurnCap} ... />
<Button disabled={atTurnCap} ... />

{atTurnCap && (
  <UpgradeOverlay
    open
    onClose={() => { /* navigate away or no-op */ }}
    copyKey="coach.cap.turns"
    inline
  />
)}

{isTrialUser && !atTurnCap && (
  <p className="text-xs text-muted-foreground">
    {t("coach.trial.turns_chip", { remaining: 5 - userTurns, total: 5 })}
  </p>
)}
```

**Step 3: Handle 403 fallback in `useCoach`**

Find the mutation that posts to `/api/coach/chat`:

```bash
grep -n "coach/chat\|useCoachChat\|mutateChat" frontend/src/hooks/useCoach.ts
```

Add error handling:

```ts
onError: (err) => {
  const code = err?.response?.data?.detail?.code;
  if (code === "coach_thread_limit" || code === "coach_turn_limit") {
    // Bubble up to component; component opens the matching overlay.
    setCapError(code);
  }
}
```

**Step 4: Manual smoke check**

1. As free user with 1 thread that has 4 user turns, send a 5th message. Reply arrives. Chip reads *"0 of 5 messages left."* Input disables.
2. Send a 6th (force via dev tools if input is disabled) → 403 → overlay opens.
3. As `offer_mode` user, send 10 messages in one thread. No cap.

**Step 5: Commit**

```bash
git add frontend/src/components/CoachChat.tsx frontend/src/hooks/useCoach.ts
git commit -m "feat(frontend): coach chat turn-cap gate + 403 fallback"
```

---

## Task 12: Frontend — `/coach` page zero-state for trial users

**Files:**
- Modify: `frontend/src/app/(protected)/coach/page.tsx`

**Step 1: Add the trial banner under the empty-positions card**

Find the branch where `optimizations.length === 0` is rendered. Add below the existing CTA:

```tsx
{isTrialUser && (
  <div className="mt-4 rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
    {t("coach.trial.intro_banner")}
  </div>
)}
```

For the `sessions.length === 0` branch (positions exist, no threads yet) add a small chip near the header: *"3 free dialogs available."*

**Step 2: Manual smoke check**

1. Free user with no optimizations → see the trial banner.
2. Free user with 1 optimization but 0 coach threads → see "3 free dialogs available."
3. Offer Mode user → no trial copy anywhere.

**Step 3: Commit**

```bash
git add frontend/src/app/\(protected\)/coach/page.tsx
git commit -m "feat(frontend): coach trial zero-state copy"
```

---

## Task 13: Frontend — Pricing page copy

**Files:**
- Modify: `frontend/src/app/pricing/page.tsx`

**Step 1: Find the Coach line on each plan card**

Run: `grep -n "Coach\|coach" frontend/src/app/pricing/page.tsx`

**Step 2: Update copy**

- **Free** card: change Coach feature line to *"Coach trial: 3 dialogs × 5 messages"* (translation key `pricing.feature.coach_trial`).
- **Job Hunter** card: same as Free.
- **Offer Mode** card: *"Coach: unlimited"* (key `pricing.feature.coach_unlimited`).

Do **not** touch CTA logic — the Downgrade / Switch plan / Subscribe behavior stays as-is.

**Step 3: Manual smoke check**

Visit `/pricing` signed out, as free, as job_hunter, as offer_mode. Copy matches in each state.

**Step 4: Commit**

```bash
git add frontend/src/app/pricing/page.tsx
git commit -m "feat(frontend): pricing page coach trial copy"
```

---

## Task 14: Translations

**Files:**
- Modify: `frontend/src/app/_lib/translations.ts`

**Step 1: Add keys (EN + RU)**

```ts
// English
"coach.cap.threads.title": "You've used all 3 free Coach dialogs",
"coach.cap.threads.body": "Upgrade to Offer Mode to keep practicing.",
"coach.cap.turns.title": "This dialog is full",
"coach.cap.turns.body": "Start a new one (you have {remaining} dialogs left) or upgrade.",
"coach.trial.threads_chip": "{remaining} of {total} dialogs left",
"coach.trial.turns_chip": "{remaining} of {total} messages left",
"coach.trial.delete_no_refund": "Deleting a dialog won't free up a slot.",
"coach.trial.intro_banner": "You'll get 3 free Coach dialogs, 5 messages each.",
"pricing.feature.coach_trial": "Coach trial: 3 dialogs × 5 messages",
"pricing.feature.coach_unlimited": "Coach: unlimited",

// Russian — translate carefully; match existing tone.
"coach.cap.threads.title": "Вы использовали все 3 бесплатных диалога с коучем",
// ... etc.
```

**Step 2: Verify no missing keys**

Run: `cd frontend && npx tsc --noEmit`
Expected: green. If the translations helper has a strict typed key set, every new key must appear in both locales.

**Step 3: Commit**

```bash
git add frontend/src/app/_lib/translations.ts
git commit -m "feat(frontend): translations for coach trial copy"
```

---

## Task 15: End-to-end manual verification

After all backend + frontend tasks are committed, run through every state once on local dev. **No automated E2E framework is installed**, so this is a manual checklist.

| State | Setup | Expected |
|---|---|---|
| Free, no optimizations | New free account | `/coach` shows intro banner, CTA → `/optimize` |
| Free, 1 optimization, 0 threads | Free, optimize 1 job | Sidebar chip "3 of 3 dialogs left"; can create thread |
| Free mid-trial | 2 threads created | Chip "1 of 3 dialogs left"; can chat |
| Free at thread cap | 3 threads created | "New thread" locked → overlay on click; existing threads readable |
| Free at turn cap | Thread with 5 user turns | Input disabled; inline overlay; new thread allowed if slots remain |
| Free, deleted thread | Delete one of 3 → still 3 in counter | "New thread" still locked (no refund — the critical test) |
| Job Hunter mid-trial | job_hunter + 2 threads | Same as free mid-trial |
| Offer Mode unlimited | offer_mode + 99 threads | No chip, no lock, no banner anywhere |
| 403 fallback | DevTools: force a stale state and send chat | Right overlay opens (matching `code`) |

Document any failures in the PR description before merging.

**Commit:**

No code commit for this task. If issues are found, file fix commits as new tasks.

---

## Out of scope (re-listed for the engineer)

These were explicitly excluded in the design and **must not** sneak into implementation:

- Weekly reset for Coach trial. Lifetime only.
- Refund on thread deletion. Counter is monotonic.
- Different model/prompt for trial users. Same `coach_system.md`, same Gemini call.
- Anonymous trial. Sign-in still required.
- Storybank or voice input for trial. `offer_mode` only.
- Backend rate limiting beyond the trial caps.
- State D header chip (the "X of 3" chip when cap is reached) — the disabled button + overlay communicate cap clearly. Easy to add later.

If any of these feel necessary while implementing, **stop and ask** — they were considered and dropped.
