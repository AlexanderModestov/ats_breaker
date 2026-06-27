# Metered Tiers & Transparent Pricing Limits — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace unlimited paid tiers + renewable Free with per-tier metered limits (optimizations + coach), reset on the Stripe billing month, and surface those limits transparently on the pricing page.

**Architecture:** One `TIER_LIMITS` table in `tiers.py` is the single source of truth. Two `profiles` counters (`period_request_count`, `coach_chats_used`) are incremented atomically via Postgres RPCs and zeroed by the `invoice.paid` webhook on each new billing cycle. Free never receives that webhook, so its counters are effectively lifetime. The existing coach "one-company lock" is removed entirely and replaced by a chat-count limit plus a per-chat message cap. The concept of "unlimited" is removed from the codebase.

**Tech Stack:** FastAPI + Pydantic backend, Supabase (Postgres) persistence, Stripe webhooks, Next.js 14 + React Query + React frontend, pytest for backend. No frontend test framework — frontend tasks use a manual smoke checklist.

**Design doc:** `docs/plans/2026-06-14-metered-tiers-design.md`

**Worktree:** `.worktrees/metered-tiers` on branch `feature/metered-tiers`.

**Final model:**

| Tier | Optimizations | Coach chats | Msgs / chat | Reset |
|------|---------------|-------------|-------------|-------|
| free | 3 | 1 | 15 | never (lifetime) |
| job_hunter | 20 | 1 | 15 | each billing month |
| offer_mode | 40 | 10 | 20 | each billing month |

**Setup before first task:**
```bash
cd .worktrees/metered-tiers
uv sync
cd frontend && npm install && cd ..
```

**Pre-existing baseline failures (NOT caused by this work; this plan supersedes them):**
- `tests/test_tiers.py` — collection error (imports `FREE_COACH_THREADS`, never added). Rewritten in Task 2.
- `tests/test_coach_routes.py::TestCoachThreadCap`, `TestCreateCoachSessionIncrementsCounter`, `TestCoachChatLazyCreateCap`, `TestCoachChatTurnCap` — dead trial-model tests. Removed/rewritten in Task 6.
- `tests/test_subscription_routes.py::TestSubscriptionCoachBlock` — old coach block shape. Rewritten in Task 7.
- `tests/test_flash_comparison.py` collection error and `tests/test_config.py::test_optimizer_version_defaults_to_v1` — **unrelated, out of scope, leave alone.**

---

## Task 1: Migration `018_metered_tiers.sql`

**Files:**
- Create: `supabase/migrations/018_metered_tiers.sql`

**Step 1: Write the migration**

```sql
-- 018_metered_tiers.sql — per-tier metered limits for optimizations + coach.
-- See docs/plans/2026-06-14-metered-tiers-design.md
-- Idempotent where practical.

-- 1. Repurpose the (never-wired) lifetime coach counter as the period coach-chat counter.
ALTER TABLE profiles RENAME COLUMN coach_threads_created_total TO coach_chats_used;

-- 2. Drop the lazy weekly-window column; reset is billing-driven now.
ALTER TABLE profiles DROP COLUMN IF EXISTS weekly_reset_at;

-- 3. Remove the dead increment RPC tied to the old column name.
DROP FUNCTION IF EXISTS increment_coach_threads_created_total(UUID);

-- 4. Atomic "consume one optimization if under limit". Returns TRUE on success.
CREATE OR REPLACE FUNCTION consume_optimization_quota(p_user_id UUID, p_limit INT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE rows_affected INT;
BEGIN
    UPDATE profiles
       SET period_request_count = period_request_count + 1
     WHERE id = p_user_id
       AND period_request_count < p_limit;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 5. Atomic "consume one coach chat if under limit". Returns TRUE on success.
CREATE OR REPLACE FUNCTION consume_coach_chat_quota(p_user_id UUID, p_limit INT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE rows_affected INT;
BEGIN
    UPDATE profiles
       SET coach_chats_used = coach_chats_used + 1
     WHERE id = p_user_id
       AND coach_chats_used < p_limit;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION consume_optimization_quota(UUID, INT) TO service_role;
GRANT EXECUTE ON FUNCTION consume_coach_chat_quota(UUID, INT) TO service_role;
```

**Step 2: Apply locally**

Run the project's local Supabase apply (e.g. `supabase db reset` or `supabase migration up` — match how prior migrations are applied here).
Expected: `profiles` has `coach_chats_used`, no `weekly_reset_at`; both RPCs present.

**Step 3: Commit**

```bash
git add supabase/migrations/018_metered_tiers.sql
git commit -m "feat(db): metered-tier counters + atomic consume RPCs"
```

---

## Task 2: `tiers.py` — `TIER_LIMITS` + helpers, remove unlimited/weekly

**Files:**
- Modify: `src/hr_breaker/services/tiers.py`
- Test: `tests/test_tiers.py` (rewrite the parts that reference removed names)

**Step 1: Write the failing test**

Replace the contents of `tests/test_tiers.py` with tests for the new API (keep any `effective_tier` / `has_feature_access` tests that still apply; the helper `_profile()` factory can stay). Core new tests:

```python
from hr_breaker.services.tiers import (
    TIER_LIMITS,
    limits_for,
    optimization_limit,
    coach_chat_limit,
    coach_msg_limit,
    effective_tier,
)


class TestTierLimits:
    def test_free_limits(self):
        assert TIER_LIMITS["free"] == {"optimizations": 3, "coach_chats": 1, "coach_msgs": 15}

    def test_job_hunter_limits(self):
        assert TIER_LIMITS["job_hunter"] == {"optimizations": 20, "coach_chats": 1, "coach_msgs": 15}

    def test_offer_mode_limits(self):
        assert TIER_LIMITS["offer_mode"] == {"optimizations": 40, "coach_chats": 10, "coach_msgs": 20}

    def test_limits_for_uses_effective_tier(self):
        # Cancelled-but-in-grace offer_mode still gets offer_mode limits.
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        p = _profile(subscription_tier="offer_mode", subscription_status="cancelled",
                     current_period_end=future)
        assert limits_for(p)["optimizations"] == 40

    def test_optimization_limit_helper(self):
        assert optimization_limit(_profile()) == 3

    def test_coach_chat_limit_helper(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_chat_limit(p) == 10

    def test_coach_msg_limit_helper(self):
        p = _profile(subscription_tier="offer_mode", subscription_status="active")
        assert coach_msg_limit(p) == 20
```

Remove any test referencing `FREE_WEEKLY_LIMIT`, `FREE_COACH_THREADS`, `FREE_COACH_TURNS`, `coach_is_unlimited`, or `maybe_reset_weekly_window`.

**Step 2: Run, verify failure**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: ImportError for the new names.

**Step 3: Implement**

In `src/hr_breaker/services/tiers.py`:
- Keep `Feature`, `TIER_RANK`, `_parse_ts`, `effective_tier`, `has_feature_access`.
- `FEATURE_MIN_TIER` stays as-is (coach already `"free"`).
- **Delete** `FREE_WEEKLY_LIMIT`, `coach_is_unlimited`, `maybe_reset_weekly_window`.
- Add:

```python
TIER_LIMITS: dict[str, dict[str, int]] = {
    "free":       {"optimizations": 3,  "coach_chats": 1,  "coach_msgs": 15},
    "job_hunter": {"optimizations": 20, "coach_chats": 1,  "coach_msgs": 15},
    "offer_mode": {"optimizations": 40, "coach_chats": 10, "coach_msgs": 20},
}


def limits_for(profile: dict) -> dict[str, int]:
    """Limits for the tier the user can currently use (honours cancellation grace)."""
    return TIER_LIMITS[effective_tier(profile)]


def optimization_limit(profile: dict) -> int:
    return limits_for(profile)["optimizations"]


def coach_chat_limit(profile: dict) -> int:
    return limits_for(profile)["coach_chats"]


def coach_msg_limit(profile: dict) -> int:
    return limits_for(profile)["coach_msgs"]
```

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_tiers.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/services/tiers.py tests/test_tiers.py
git commit -m "feat(tiers): TIER_LIMITS source of truth; drop unlimited + weekly window"
```

---

## Task 3: `access_control.py` — metered quota for all tiers

**Files:**
- Modify: `src/hr_breaker/services/access_control.py`
- Test: `tests/test_access_control.py`

**Step 1: Write the failing tests**

Rewrite `tests/test_access_control.py` quota tests around the new function `check_optimization_quota(email, profile)`:

```python
from hr_breaker.services.access_control import check_optimization_quota


def _p(tier="free", status="none", used=0, period_end=None):
    return {
        "subscription_tier": tier, "subscription_status": status,
        "current_period_end": period_end, "period_request_count": used,
    }


class TestOptimizationQuota:
    def test_free_under_limit(self):
        r = check_optimization_quota("u@x.com", _p(used=1))
        assert r.allowed and r.remaining == 2

    def test_free_at_limit_blocked(self):
        r = check_optimization_quota("u@x.com", _p(used=3))
        assert not r.allowed and r.remaining == 0 and r.reason == "quota_exhausted"

    def test_free_renewal_date_is_none(self):
        r = check_optimization_quota("u@x.com", _p(used=3))
        assert r.renewal_date is None  # Free never resets

    def test_job_hunter_metered(self):
        r = check_optimization_quota("u@x.com", _p(tier="job_hunter", status="active", used=19))
        assert r.allowed and r.remaining == 1

    def test_job_hunter_at_limit_blocked_with_renewal(self):
        end = "2099-01-01T00:00:00+00:00"
        r = check_optimization_quota("u@x.com", _p(tier="job_hunter", status="active", used=20, period_end=end))
        assert not r.allowed and r.renewal_date is not None

    def test_admin_allowlist_bypasses(self, monkeypatch):
        from hr_breaker.services import access_control
        monkeypatch.setattr(access_control, "_is_unlimited", lambda e: True)
        r = check_optimization_quota("admin@x.com", _p(used=999))
        assert r.allowed
```

Remove tests referencing `check_quota`, `consume_request`, `.unlimited`, `weekly_reset_at`.

**Step 2: Run, verify failure**

Run: `uv run pytest tests/test_access_control.py -v`
Expected: ImportError / failures.

**Step 3: Implement**

Rewrite `src/hr_breaker/services/access_control.py`:
- Drop `unlimited` field from `AccessResult` (and from `to_dict`).
- Delete `check_quota`, `consume_request`, and the `maybe_reset_weekly_window` import.
- Keep `_is_unlimited`, `check_feature_access` (drop its `unlimited=True` → just `allowed=True`).
- Add:

```python
from hr_breaker.services.tiers import (
    Feature,
    FEATURE_MIN_TIER,
    effective_tier,
    has_feature_access,
    optimization_limit,
)


def check_optimization_quota(email: str, profile: dict) -> AccessResult:
    """Metered optimization quota for every tier."""
    if _is_unlimited(email):
        return AccessResult(allowed=True, remaining=None)

    limit = optimization_limit(profile)
    used = profile.get("period_request_count", 0)
    remaining = max(0, limit - used)
    # Paid tiers renew at the billing-period end; Free never renews.
    renewal = None
    if effective_tier(profile) != "free":
        renewal = _parse_ts(profile.get("current_period_end"))

    if used >= limit:
        return AccessResult(
            allowed=False, remaining=0,
            reason="quota_exhausted", renewal_date=renewal,
        )
    return AccessResult(allowed=True, remaining=remaining, renewal_date=renewal)
```

Add `from hr_breaker.services.tiers import effective_tier, _parse_ts` (or re-import `_parse_ts`; if it is private, add a thin local parse helper instead to avoid importing a private name — match existing style).

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_access_control.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/services/access_control.py tests/test_access_control.py
git commit -m "feat(access): metered optimization quota across all tiers; drop unlimited"
```

---

## Task 4: `supabase.py` — atomic consume wrappers + coach turn counter

**Files:**
- Modify: `src/hr_breaker/services/supabase.py`
- Test: `tests/test_coach_routes.py` (unit-level on the service is optional; primary coverage is via routes in Tasks 5–6)

**Step 1: Implement the two RPC wrappers**

Add methods on `SupabaseService` (near the other coach/profile helpers):

```python
def consume_optimization_quota(self, user_id: str, limit: int) -> bool:
    """Atomically consume one optimization. False if at/over limit."""
    try:
        res = self._client.rpc(
            "consume_optimization_quota",
            {"p_user_id": user_id, "p_limit": limit},
        ).execute()
        return bool(res.data)
    except Exception as e:
        logger.error(f"consume_optimization_quota failed: {e}")
        raise SupabaseError(str(e)) from e


def consume_coach_chat_quota(self, user_id: str, limit: int) -> bool:
    """Atomically consume one coach chat. False if at/over limit."""
    try:
        res = self._client.rpc(
            "consume_coach_chat_quota",
            {"p_user_id": user_id, "p_limit": limit},
        ).execute()
        return bool(res.data)
    except Exception as e:
        logger.error(f"consume_coach_chat_quota failed: {e}")
        raise SupabaseError(str(e)) from e
```

**Step 2: Remove the now-stale company-lock helpers**

Delete `get_coach_lock` and `get_coach_locked_company` (lines ~456–495) — they back the removed company-lock model. Fix the `create_coach_session` docstring (drop "and bump the lifetime counter"; the bump now happens via the RPC at the route layer, not here).

> Note: `get_coach_lock` is only consumed by `coach.py` (`_check_company_cap`) and `subscription.py`; both are rewritten in Tasks 6–7. Confirm with `grep -rn "get_coach_lock" src/` before deleting.

**Step 3: Verify nothing else imports the removed helpers**

Run: `grep -rn "get_coach_lock\|get_coach_locked_company\|increment_coach_threads" src/ tests/`
Expected: only Tasks 6–7 files (handled there).

**Step 4: Commit**

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "feat(supabase): atomic quota consume RPCs; remove coach company-lock helpers"
```

---

## Task 5: Optimize route — atomic metered consume

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py:18,288-313`
- Test: `tests/test_optimize_routes.py` (find the existing optimize route test file; if none, add a focused one mirroring `test_coach_routes.py` fixtures)

**Step 1: Write failing tests**

For the start-optimization endpoint:

```python
class TestOptimizeQuota:
    def test_free_at_limit_returns_402(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 3,
        }
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 402
        assert r.json()["detail"]["reason"] == "quota_exhausted"

    def test_consume_called_then_run_starts(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "job_hunter", "subscription_status": "active",
            "current_period_end": "2099-01-01T00:00:00+00:00", "period_request_count": 5,
        }
        fake_supabase.consume_optimization_quota.return_value = True
        fake_supabase.get_cv.return_value = {"id": "c1", "content_text": "cv"}
        fake_supabase.create_optimization_run.return_value = {"id": "r1"}
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 200
        fake_supabase.consume_optimization_quota.assert_called_once_with(USER, 20)

    def test_lost_race_returns_402(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "id": USER, "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 2,
        }
        fake_supabase.consume_optimization_quota.return_value = False  # raced to limit
        fake_supabase.get_cv.return_value = {"id": "c1", "content_text": "cv"}
        r = client.post("/api/optimize", json={"cv_id": "c1", "job_input": "..."})
        assert r.status_code == 402
```

**Step 2: Run, verify failure**

Run: `uv run pytest tests/test_optimize_routes.py::TestOptimizeQuota -v`

**Step 3: Implement**

In `optimize.py`:
- Change import (line 18) to:
  ```python
  from hr_breaker.services.access_control import check_optimization_quota
  from hr_breaker.services.tiers import optimization_limit
  ```
- Replace lines 290–292:
  ```python
  quota = check_optimization_quota(user_email or "", profile)
  if not quota.allowed:
      raise HTTPException(status_code=402, detail=quota.to_dict())
  ```
- Replace the `consume_request` block (lines 310–313) — consume atomically **before** creating the run, and 402 on a lost race. Skip consume for admin allowlist:
  ```python
  from hr_breaker.services.access_control import _is_unlimited
  ...
  if not _is_unlimited(user_email or ""):
      ok = supabase.consume_optimization_quota(user_id, optimization_limit(profile))
      if not ok:
          raise HTTPException(
              status_code=402,
              detail={"allowed": False, "remaining": 0, "reason": "quota_exhausted"},
          )
  run = supabase.create_optimization_run(...)  # move run creation AFTER the consume
  ```
  (Reorder so `create_optimization_run` runs only after a successful consume.)

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_optimize_routes.py -v`

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/optimize.py tests/test_optimize_routes.py
git commit -m "feat(optimize): atomic metered quota consume with 402 on exhaustion"
```

---

## Task 6: Coach route — remove company-lock, add chat-count + message caps

**Files:**
- Modify: `src/hr_breaker/api/routes/coach.py`
- Test: `tests/test_coach_routes.py`

**Step 1: Rewrite the coach-cap tests**

Delete the dead classes `TestCreateCoachSessionIncrementsCounter`, `TestCoachThreadCap`, `TestCoachChatLazyCreateCap`, `TestCoachChatTurnCap` and any company-lock tests. Add:

```python
def _profile(tier="free", status="none", chats_used=0, period_end=None):
    return {
        "id": USER, "subscription_tier": tier, "subscription_status": status,
        "current_period_end": period_end, "coach_chats_used": chats_used,
    }


class TestCoachChatCap:
    def test_free_under_cap_can_create(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=0)
        fake_supabase.consume_coach_chat_quota.return_value = True
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "s1", "optimization_run_id": "r1", "title": None,
            "last_message_at": None, "created_at": "2026-06-14T00:00:00Z",
            "updated_at": "2026-06-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201
        fake_supabase.consume_coach_chat_quota.assert_called_once_with(USER, 1)

    def test_free_at_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.consume_coach_chat_quota.return_value = False
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 402
        assert r.json()["detail"]["code"] == "coach_chat_limit"

    def test_offer_mode_cap_is_10(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(tier="offer_mode", status="active", chats_used=3)
        fake_supabase.consume_coach_chat_quota.return_value = True
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.create_coach_session.return_value = {
            "id": "s1", "optimization_run_id": "r1", "title": None, "last_message_at": None,
            "created_at": "2026-06-14T00:00:00Z", "updated_at": "2026-06-14T00:00:00Z",
        }
        r = client.post("/api/coach/sessions", json={"optimization_run_id": "r1"})
        assert r.status_code == 201
        fake_supabase.consume_coach_chat_quota.assert_called_once_with(USER, 10)


class TestCoachTurnCap:
    @staticmethod
    def _history(n_user_turns: int) -> list[dict]:
        msgs = []
        for i in range(n_user_turns):
            msgs.append({"kind": "request", "parts": [{"part_kind": "user-prompt", "content": f"q{i}"}]})
            msgs.append({"kind": "response", "parts": [{"part_kind": "text", "content": f"a{i}"}]})
        return msgs

    def test_free_under_turn_cap_passes(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        fake_supabase.get_coach_messages.return_value = self._history(14)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200

    def test_free_at_turn_cap_blocked(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_coach_messages.return_value = self._history(15)
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 402
        assert r.json()["detail"]["code"] == "coach_turn_limit"

    def test_offer_mode_turn_cap_is_20(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = _profile(tier="offer_mode", status="active", chats_used=1)
        fake_supabase.get_coach_session.return_value = {"id": "s1", "user_id": USER, "optimization_run_id": "r1"}
        fake_supabase.get_coach_messages.return_value = self._history(19)
        fake_supabase.get_optimization_run.return_value = {"id": "r1", "user_id": USER, "job_parsed": {}}
        fake_supabase.get_cv.return_value = None
        r = client.post("/api/coach/chat", json={"thread_id": "s1", "message": "hi"})
        assert r.status_code == 200
```

**Step 2: Run, verify failures**

Run: `uv run pytest tests/test_coach_routes.py -v`

**Step 3: Implement**

In `src/hr_breaker/api/routes/coach.py`:
- Replace the import `from hr_breaker.services.tiers import coach_is_unlimited` with:
  ```python
  from hr_breaker.services.tiers import coach_chat_limit, coach_msg_limit
  from hr_breaker.services.access_control import _is_unlimited
  ```
- **Delete** `_COMPANY_CAP_ERROR` and `_check_company_cap` (lines 83–111).
- Add a chat-quota helper and a turn-cap helper near the top:
  ```python
  _CHAT_LIMIT_ERROR = {
      "code": "coach_chat_limit",
      "message": "You've used all your coach chats for this period.",
  }
  _TURN_LIMIT_ERROR = {
      "code": "coach_turn_limit",
      "message": "This chat has reached its message limit. Start a new chat.",
  }


  def _consume_chat_or_402(profile, supabase, user_id, email):
      """Atomically reserve a coach-chat slot; raise 402 if none left."""
      if _is_unlimited(email):
          return
      if not supabase.consume_coach_chat_quota(user_id, coach_chat_limit(profile)):
          raise HTTPException(status_code=402, detail=_CHAT_LIMIT_ERROR)


  def _check_turn_cap(profile, raw_history, email) -> None:
      if _is_unlimited(email):
          return
      user_turns = sum(
          1
          for msg in (raw_history or [])
          if msg.get("kind") == "request"
          for part in msg.get("parts", [])
          if part.get("part_kind") == "user-prompt"
      )
      if user_turns >= coach_msg_limit(profile):
          raise HTTPException(status_code=402, detail=_TURN_LIMIT_ERROR)
  ```
- `create_thread`: replace `_check_company_cap(...)` with the consume call. The route needs the email — add `CurrentUserWithEmail` (see how `subscription.py` injects it) or fetch via deps. Use the same dependency style already used for email in this codebase:
  ```python
  async def create_thread(body, user, supabase):   # user: CurrentUserWithEmail
      user_id, user_email = user
      profile = supabase.get_profile(user_id) or {}
      run = get_run_or_404(supabase, body.optimization_run_id, user_id)
      _consume_chat_or_402(profile, supabase, user_id, user_email or "")
      session = supabase.create_coach_session(user_id, body.optimization_run_id)
      return {**session, "preview": None, "message_count": 0}
  ```
- `chat`: switch to `CurrentUserWithEmail`. In the lazy-create branch replace `_check_company_cap(...)` with `_consume_chat_or_402(...)` (consume BEFORE `create_coach_session`). For the existing-thread branch, after loading `raw_history` (line ~195), call `_check_turn_cap(profile, raw_history, user_email or "")` — load `profile` once at the top of `chat`. Make sure the turn check runs before the agent stream starts so the cap returns 402 cleanly rather than mid-stream.

> Note: the existing-thread path already loads `raw_history` for the agent; reuse that single load for the turn check — don't add a second query.

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_coach_routes.py -v`
Expected: green.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/coach.py tests/test_coach_routes.py
git commit -m "feat(coach): chat-count + per-chat message caps; remove company-lock"
```

---

## Task 7: Subscription route — new quota response shape

**Files:**
- Modify: `src/hr_breaker/api/routes/subscription.py:14-87`
- Test: `tests/test_subscription_routes.py`

**Step 1: Rewrite the response tests**

Replace `TestSubscriptionCoachBlock`:

```python
class TestSubscriptionStatusShape:
    def test_free_response(self, client, fake_supabase):
        fake_supabase.get_profile.return_value = {
            "subscription_tier": "free", "subscription_status": "none",
            "current_period_end": None, "period_request_count": 1, "coach_chats_used": 0,
        }
        body = client.get("/api/subscription").json()
        assert body["tier"] == "free"
        assert body["optimizations"] == {"used": 1, "limit": 3, "remaining": 2, "renews_at": None}
        assert body["coach"] == {"chats_used": 0, "chats_limit": 1, "msgs_per_chat": 15}
        assert "is_unlimited" not in body
        assert "weekly_reset_at" not in body

    def test_offer_mode_response(self, client, fake_supabase):
        end = "2099-01-01T00:00:00+00:00"
        fake_supabase.get_profile.return_value = {
            "subscription_tier": "offer_mode", "subscription_status": "active",
            "current_period_end": end, "period_request_count": 12, "coach_chats_used": 3,
        }
        body = client.get("/api/subscription").json()
        assert body["optimizations"] == {"used": 12, "limit": 40, "remaining": 28, "renews_at": end}
        assert body["coach"] == {"chats_used": 3, "chats_limit": 10, "msgs_per_chat": 20}
```

**Step 2: Run, verify failure**

Run: `uv run pytest tests/test_subscription_routes.py -v`

**Step 3: Implement**

In `subscription.py`:
- Imports: drop `coach_is_unlimited` and `check_quota`; add `from hr_breaker.services.tiers import limits_for, effective_tier`.
- Replace the response models:
  ```python
  class OptimizationsBlock(BaseModel):
      used: int
      limit: int
      remaining: int
      renews_at: str | None


  class CoachBlock(BaseModel):
      chats_used: int
      chats_limit: int
      msgs_per_chat: int


  class SubscriptionStatusResponse(BaseModel):
      tier: str
      status: str
      optimizations: OptimizationsBlock
      coach: CoachBlock
      current_period_end: str | None
  ```
- Rewrite `get_subscription_status` body:
  ```python
  profile = get_profile_or_404(supabase, user_id)
  limits = limits_for(profile)
  tier = effective_tier(profile)
  opt_used = profile.get("period_request_count", 0)
  chats_used = profile.get("coach_chats_used", 0)
  renews_at = None if tier == "free" else profile.get("current_period_end")
  return SubscriptionStatusResponse(
      tier=tier,
      status=profile.get("subscription_status", "none"),
      optimizations=OptimizationsBlock(
          used=opt_used, limit=limits["optimizations"],
          remaining=max(0, limits["optimizations"] - opt_used), renews_at=renews_at,
      ),
      coach=CoachBlock(
          chats_used=chats_used, chats_limit=limits["coach_chats"],
          msgs_per_chat=limits["coach_msgs"],
      ),
      current_period_end=profile.get("current_period_end"),
  )
  ```
  Remove the `get_coach_locked_company` call and the admin-bypass branch on `remaining` (admin allowlist still works at enforcement time; the status endpoint just reports the tier's numbers).

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_subscription_routes.py -v`

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/subscription.py tests/test_subscription_routes.py
git commit -m "feat(api): metered quota shape in /api/subscription"
```

---

## Task 8: Webhooks — billing-cycle reset + upgrade reset

**Files:**
- Modify: `src/hr_breaker/api/routes/webhooks.py`
- Modify: `src/hr_breaker/services/stripe_service.py` (only if a `billing_reason` / period helper is missing)
- Test: `tests/test_webhooks.py` (find existing; add cases)

**Step 1: Write failing tests**

```python
class TestBillingReset:
    def test_invoice_paid_cycle_resets_counters(self, client, fake_supabase, fake_stripe):
        # Construct an invoice.paid event with billing_reason="subscription_cycle".
        # Assert update_profile called with period_request_count=0 and coach_chats_used=0.
        ...

    def test_invoice_paid_create_does_not_reset(self, ...):
        # billing_reason="subscription_create" → no reset.
        ...

    def test_checkout_completed_zeroes_quota_on_upgrade(self, ...):
        # checkout.session.completed → update includes period_request_count=0, coach_chats_used=0.
        ...

    def test_subscription_deleted_does_not_reset_counters(self, ...):
        # customer.subscription.deleted → update has NO period_request_count / coach_chats_used keys.
        ...
```

Match the existing webhook-test construction style (how the suite fakes `construct_webhook_event`). If `test_webhooks.py` does not exist, add it mirroring the `StripeService` mocking already used elsewhere.

**Step 2: Run, verify failure**

Run: `uv run pytest tests/test_webhooks.py -v`

**Step 3: Implement**

In `webhooks.py`:
- **`checkout.session.completed`** (line ~58 `update_profile`): add `"period_request_count": 0` and `"coach_chats_used": 0` to the update dict (fresh quota on upgrade).
- **`customer.subscription.deleted`** (lines ~107–116): remove `"period_request_count": 0` and `"weekly_reset_at": ...`. Keep only tier/status/subscription_id/current_period_end resets. (Anti-abuse: do not refund Free quota.)
- Add a new branch (after the deleted branch, before `invoice.payment_failed`):
  ```python
  elif event.type == "invoice.paid":
      invoice = event.data.object
      if getattr(invoice, "billing_reason", None) != "subscription_cycle":
          return {"status": "ok"}
      sub_id = getattr(invoice, "subscription", None)
      if not sub_id:
          return {"status": "ok"}
      subscription = stripe_service.get_subscription(sub_id)
      user_id = subscription.metadata.get("user_id") if subscription.metadata else None
      if not user_id:
          return {"status": "ok"}
      period_end = datetime.fromtimestamp(
          stripe_service.get_period_end(subscription), tz=timezone.utc
      )
      supabase.update_profile(user_id, {
          "period_request_count": 0,
          "coach_chats_used": 0,
          "current_period_end": period_end.isoformat(),
      })
      logger.info(f"Reset metered quota for user {user_id} on new billing cycle")
  ```
- Remove the now-unused `timedelta` import if nothing else uses it.

**Step 4: Run, verify pass**

Run: `uv run pytest tests/test_webhooks.py -v`

**Step 5: Full backend suite**

Run: `uv run pytest tests/ -q --ignore=tests/test_flash_comparison.py --ignore=tests/test_optimizer_comparison.py`
Expected: green except the pre-existing unrelated `test_config.py::test_optimizer_version_defaults_to_v1`.

**Step 6: Commit**

```bash
git add src/hr_breaker/api/routes/webhooks.py tests/test_webhooks.py
git commit -m "feat(webhooks): billing-cycle quota reset; fresh quota on upgrade; no refund on downgrade"
```

---

## Task 9: Frontend — mirror `TIER_LIMITS`

**Files:**
- Modify: `frontend/src/lib/tiers.ts`

**Step 1: Add the limits map**

```ts
export const TIER_LIMITS: Record<Tier, { optimizations: number; coachChats: number; coachMsgs: number }> = {
  free:       { optimizations: 3,  coachChats: 1,  coachMsgs: 15 },
  job_hunter: { optimizations: 20, coachChats: 1,  coachMsgs: 15 },
  offer_mode: { optimizations: 40, coachChats: 10, coachMsgs: 20 },
};
```

**Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: green.

**Step 3: Commit**

```bash
git add frontend/src/lib/tiers.ts
git commit -m "feat(frontend): mirror TIER_LIMITS"
```

---

## Task 10: Frontend — `SubscriptionStatus` type

**Files:**
- Modify: `frontend/src/types/index.ts:133-143`

**Step 1: Replace the interface**

```ts
export interface SubscriptionStatus {
  tier: Tier;
  status: "none" | "active" | "cancelled";
  optimizations: {
    used: number;
    limit: number;
    remaining: number;
    renews_at: string | null;
  };
  coach: {
    chats_used: number;
    chats_limit: number;
    msgs_per_chat: number;
  };
  current_period_end: string | null;
}
```

(Import `Tier` from `@/lib/tiers` if not already.)

**Step 2: Type-check to surface broken consumers**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors in `QuotaBanner.tsx`, `useCoachTrialStatus.ts`, `optimize/page.tsx`, `CoachSidebar.tsx`, `AddPositionDialog.tsx` — fixed in Tasks 11–13. Do not fix unrelated code.

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): metered SubscriptionStatus type"
```

---

## Task 11: Frontend — coach quota hook (replace company-lock)

**Files:**
- Replace: `frontend/src/hooks/useCoachTrialStatus.ts`
- Modify consumers: `frontend/src/components/coach/AddPositionDialog.tsx`, `frontend/src/components/coach/CoachSidebar.tsx`

**Step 1: Rewrite the hook around chat-count, not company-lock**

```ts
"use client";

import { useSubscription } from "@/hooks/useSubscription";

/** Coach quota derived from the subscription (chats remaining + per-chat message cap). */
export function useCoachQuota() {
  const { data: sub } = useSubscription();
  const chatsUsed = sub?.coach.chats_used ?? 0;
  const chatsLimit = sub?.coach.chats_limit ?? 0;
  const chatsRemaining = Math.max(0, chatsLimit - chatsUsed);
  const msgsPerChat = sub?.coach.msgs_per_chat ?? 0;
  return {
    chatsUsed,
    chatsLimit,
    chatsRemaining,
    msgsPerChat,
    atChatCap: !!sub && chatsRemaining <= 0,
  };
}
```

Delete the old `useCoachTrialStatus` export (rename file or replace export — update both consumers).

**Step 2: Update consumers**

- `AddPositionDialog.tsx` and `CoachSidebar.tsx`: remove all `isPositionLocked` / `lockedCompany` / company-lock UI. Replace with the new-chat gate using `useCoachQuota().atChatCap` — when at cap, the "New chat / Add position" CTA opens the pricing modal (free/job_hunter) or shows a "renews on N" note (offer_mode). Reuse `usePricingModal()` as `QuotaBanner` does.
- Add a scarcity chip: `{chatsRemaining} of {chatsLimit} chats left` (translation key, Task 15).

**Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`

**Step 4: Manual smoke**

Start backend + frontend. As a free user with `coach_chats_used=0`: sidebar shows "1 of 1 chats left", can create a chat. After creating one: "0 of 1 chats left", New-chat CTA opens pricing modal. As offer_mode with `coach_chats_used=10`: CTA shows "renews on N", no upgrade button.

**Step 5: Commit**

```bash
git add frontend/src/hooks/useCoachTrialStatus.ts frontend/src/components/coach/AddPositionDialog.tsx frontend/src/components/coach/CoachSidebar.tsx
git commit -m "feat(frontend): coach chat-quota gate; remove company-lock UI"
```

---

## Task 12: Frontend — `QuotaBanner` for all tiers

**Files:**
- Modify: `frontend/src/components/QuotaBanner.tsx`
- Check: `frontend/src/app/(protected)/optimize/page.tsx` (any `is_unlimited` / `remaining` / `weekly_reset_at` usage)

**Step 1: Rewrite to read the new shape and apply to every tier**

```tsx
export function QuotaBanner() {
  const { data: sub } = useSubscription();
  const { open } = usePricingModal();
  if (!sub) return null;

  const { remaining, renews_at } = sub.optimizations;
  if (remaining > 1) return null;

  const days = daysUntil(renews_at);
  const isTopTier = sub.tier === "offer_mode";
  const renewMsg = renews_at ? `Renews in ${days} day${days === 1 ? "" : "s"}.` : "";

  if (remaining === 1) {
    return (/* amber "Last optimization {period}." — upgrade link only if !isTopTier */);
  }
  return (/* red "Limit reached. {renewMsg}" — upgrade link only if !isTopTier && tier!=="free" shows upgrade; free always shows upgrade */);
}
```

Rules:
- Free: "X total" framing; always show upgrade link (no renewal).
- Job Hunter: show upgrade link + "Renews in N days".
- Offer Mode: no upgrade link; only "Renews in N days".

**Step 2: Fix `optimize/page.tsx`** any references to `sub.is_unlimited` / `sub.remaining` / `sub.weekly_reset_at` → use `sub.optimizations.*`.

**Step 3: Type-check + smoke**

Run: `cd frontend && npx tsc --noEmit`
Smoke: free at 0/3 → red banner, upgrade link, no renewal. job_hunter at 19/20 → amber. job_hunter 20/20 → red with renewal + upgrade. offer_mode 40/40 → red with renewal, no upgrade.

**Step 4: Commit**

```bash
git add frontend/src/components/QuotaBanner.tsx "frontend/src/app/(protected)/optimize/page.tsx"
git commit -m "feat(frontend): metered QuotaBanner across all tiers"
```

---

## Task 13: Frontend — coach chat turn-cap UI + 402 handling

**Files:**
- Modify: `frontend/src/components/coach/CoachChat.tsx` (find the chat input/message-list component used by the coach page)
- Modify: the coach chat mutation hook (e.g. `frontend/src/hooks/useCoach*.ts`)

**Step 1: Turn-cap gate**

```tsx
const { msgsPerChat } = useCoachQuota();
const userTurns = messages.filter((m) => m.role === "user").length;
const atTurnCap = msgsPerChat > 0 && userTurns >= msgsPerChat;
// disable input + send button when atTurnCap; show chip "{msgsPerChat - userTurns} of {msgsPerChat} messages left"
```

**Step 2: 402 fallback**

In the chat mutation `onError`, read `err.response.data.detail.code`; on `"coach_turn_limit"` or `"coach_chat_limit"` open the matching upsell/notice (pricing modal for free/job_hunter; "renews on N" notice for offer_mode).

**Step 3: Type-check + smoke**

Free chat with 14 user turns: chip "1 of 15 left", send works; at 15 → input disabled. Offer Mode: cap at 20.

**Step 4: Commit**

```bash
git add frontend/src/components/coach/CoachChat.tsx frontend/src/hooks/
git commit -m "feat(frontend): coach turn-cap UI + 402 handling"
```

---

## Task 14: Frontend — Pricing page transparent limits

**Files:**
- Modify: `frontend/src/components/PricingContent.tsx:49-62` (and the Offer Mode card's feature list)

**Step 1: Replace the feature lines with concrete numbers**

- Free card: `"3 resume optimizations / week"` → `"3 resume optimizations total"`; add `"Coach: 1 chat, 15 messages"`.
- Job Hunter card: `"Unlimited resume optimizations"` → `"20 optimizations / month"`; add `"Coach: 1 chat, 15 messages"`.
- Offer Mode card: set `"40 optimizations / month"` and `"Coach: 10 chats, 20 messages each"`.

Pull numbers from `TIER_LIMITS` (Task 9) rather than hardcoding where the card already maps over a features array; otherwise inline the strings to match existing card structure. Keep all CTA logic untouched.

**Step 2: Type-check + smoke**

Run: `cd frontend && npx tsc --noEmit`
Visit `/pricing` (and the pricing modal) signed out and as each tier — numbers match the table.

**Step 3: Commit**

```bash
git add frontend/src/components/PricingContent.tsx
git commit -m "feat(frontend): transparent per-tier limits on pricing"
```

---

## Task 15: Frontend — translations

**Files:**
- Modify: `frontend/src/app/_lib/translations.ts` (the project's translation source — confirm path via grep `t(` usage)

**Step 1: Add EN + RU keys** for: chats-left chip, messages-left chip, chat-cap notice (upsell vs top-tier renews), turn-cap notice, pricing feature lines. Match existing key naming and tone.

**Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: green (every new key present in both locales if the helper is typed).

**Step 3: Commit**

```bash
git add frontend/src/app/_lib/translations.ts
git commit -m "feat(frontend): translations for metered-tier copy"
```

---

## Task 16: End-to-end manual verification

No automated E2E. Run each state once on local dev (set `profiles` values directly in Supabase).

| State | Setup | Expected |
|---|---|---|
| Free optimizations remaining | `tier=free, period_request_count=1` | QuotaBanner hidden until 1 left; "3 total" framing |
| Free optimizations exhausted | `period_request_count=3` | 402 on start; red banner, upgrade link, **no** renewal date |
| Free coach chat available | `coach_chats_used=0` | Can create 1 chat; chip "1 of 1" |
| Free coach chat exhausted | `coach_chats_used=1` | New-chat CTA → pricing modal (402 `coach_chat_limit`) |
| Free coach turn cap | chat with 15 user turns | input disabled; 402 `coach_turn_limit` |
| Free delete chat (no refund) | create 1, delete it | `coach_chats_used` still 1; cannot create another |
| Job Hunter metered | `tier=job_hunter, period_request_count=20` | 402; banner shows renewal date + upgrade to Offer Mode |
| Offer Mode metered | `tier=offer_mode, period_request_count=40` | 402; banner shows renewal date, **no** upgrade link |
| Offer Mode coach | `coach_chats_used=10` | New-chat blocked with "renews on N", no upgrade |
| Billing cycle reset | simulate `invoice.paid` (Stripe CLI / test event) `billing_reason=subscription_cycle` | both counters → 0 |
| Upgrade Free→paid | `period_request_count=3` then checkout | after `checkout.session.completed`, counters → 0, fresh paid quota |
| Downgrade to Free | cancel + `subscription.deleted` | counters **preserved** (no refund) |

Document any failures in the PR description before merging.

---

## Out of Scope (do not implement)

- Legal disclaimers / acceptable-use copy (user chose numbers-only).
- Lazy `current_period_end` safety-net for missed `invoice.paid` webhooks.
- Quota rollover between months.
- Annual billing.
- The unrelated pre-existing failures: `test_config.py::test_optimizer_version_defaults_to_v1`, `test_flash_comparison.py` collection error.
- Removing the dead `consume_request` SQL function from migration 006 (pre-existing dead code; leave unless asked).
