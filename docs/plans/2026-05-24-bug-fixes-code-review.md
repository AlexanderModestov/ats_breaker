# Code Review Bug Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 confirmed/plausible bugs identified in the code review: broken Supabase UPDATE, empty-string email stored in DB, TOCTOU race on profile creation, and AuthError escaping JWT handler.

**Architecture:** Surgical fixes only — one file per task where possible. No behaviour changes beyond fixing the stated bugs.

**Tech Stack:** Python 3.11, FastAPI, supabase-py v2, python-jose

---

## Task 1: Fix link_telegram and update_profile always raising SupabaseError

**Files:**
- Modify: `src/hr_breaker/services/supabase.py`

**Root cause:** `supabase-py` `.update().eq().execute()` without `.select()` returns `data=[]`
even on a successful update. The `if not result.data` check therefore always fires and
raises `SupabaseError`, breaking Telegram linking and profile updates for all users.

**Fix:** Add `.select()` before `.execute()` in both methods.

### Step 1: Fix `link_telegram`

In `supabase.py`, find `link_telegram` (~line 611). Change:

```python
result = (
    self._client.table("profiles")
    .update({"telegram_id": telegram_id})
    .eq("id", user_id)
    .execute()
)
if not result.data:
    raise SupabaseError(f"No profile found for user_id={user_id}")
```

To:

```python
result = (
    self._client.table("profiles")
    .update({"telegram_id": telegram_id})
    .eq("id", user_id)
    .select()
    .execute()
)
if not result.data:
    raise SupabaseError(f"No profile found for user_id={user_id}")
```

### Step 2: Fix `update_profile`

In `supabase.py`, find `update_profile` (~line 80). Change:

```python
result = (
    self._client.table("profiles")
    .update(data)
    .eq("id", user_id)
    .execute()
)
if not result.data:
    raise SupabaseError(f"No profile found for user_id={user_id}")
return result.data[0]
```

To:

```python
result = (
    self._client.table("profiles")
    .update(data)
    .eq("id", user_id)
    .select()
    .execute()
)
if not result.data:
    raise SupabaseError(f"No profile found for user_id={user_id}")
return result.data[0]
```

### Step 3: Verify compiles

```
cd C:/Users/aleks/Documents/Projects/hr-breaker && python -m py_compile src/hr_breaker/services/supabase.py && echo OK
```

Expected: `OK`

### Step 4: Commit

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "fix(supabase): add .select() to update_profile and link_telegram so result.data is populated"
```

---

## Task 2: Fix empty-string email stored when email is None

**Files:**
- Modify: `src/hr_breaker/services/supabase.py`
- Modify: `src/hr_breaker/api/routes/telegram.py`
- Modify: `src/hr_breaker/api/routes/users.py`

**Root cause:** Both `/link` and `/me` routes call `create_profile(user_id, email or "")`.
When `email` is `None` (bot-auth users), an empty string `""` is stored in `profiles.email`,
breaking any downstream flow that calls `generate_magiclink(email)` with a blank address.

**Fix:** Allow `create_profile` to accept `None` for email and pass it through; remove `or ""` from callers.

### Step 1: Update `create_profile` signature

In `supabase.py` ~line 98, change:

```python
def create_profile(self, user_id: str, email: str, name: str | None = None) -> dict[str, Any]:
```

To:

```python
def create_profile(self, user_id: str, email: str | None, name: str | None = None) -> dict[str, Any]:
```

The body stays the same — `email` of `None` will store `NULL` in Postgres (correct behaviour).

### Step 2: Fix `/link` route caller

In `src/hr_breaker/api/routes/telegram.py` ~line 83, change:

```python
supabase.create_profile(user_id, email or "")
```

To:

```python
supabase.create_profile(user_id, email)
```

### Step 3: Fix `/me` route caller

In `src/hr_breaker/api/routes/users.py` ~line 42, change:

```python
profile = supabase.create_profile(user_id, email or "")
```

To:

```python
profile = supabase.create_profile(user_id, email)
```

### Step 4: Verify compiles

```
cd C:/Users/aleks/Documents/Projects/hr-breaker && python -m py_compile src/hr_breaker/services/supabase.py src/hr_breaker/api/routes/telegram.py src/hr_breaker/api/routes/users.py && echo OK
```

Expected: `OK`

### Step 5: Commit

```bash
git add src/hr_breaker/services/supabase.py src/hr_breaker/api/routes/telegram.py src/hr_breaker/api/routes/users.py
git commit -m "fix(auth): store NULL instead of empty string when email is missing on profile creation"
```

---

## Task 3: Fix TOCTOU race — two concurrent /link requests create duplicate profile

**Files:**
- Modify: `src/hr_breaker/api/routes/telegram.py`

**Root cause:** The `/link` route does:
1. `get_profile(user_id)` → returns `None`
2. `create_profile(user_id, email)` → INSERT

Two concurrent requests both pass step 1 before either completes step 2. The second
INSERT hits a primary-key conflict and raises `SupabaseError` → 500.

**Fix:** Catch `SupabaseError` from `create_profile` and check if the profile now exists
(the concurrent request created it). If it does, continue normally. This is the
"optimistic concurrency" approach — try, catch conflict, verify state.

### Step 1: Wrap `create_profile` call

In `telegram.py`, replace the current profile creation block:

```python
profile = supabase.get_profile(user_id)
if not profile:
    supabase.create_profile(user_id, email)
```

With:

```python
profile = supabase.get_profile(user_id)
if not profile:
    try:
        supabase.create_profile(user_id, email)
    except SupabaseError:
        # Concurrent request may have created the profile; verify before failing
        if not supabase.get_profile(user_id):
            raise
```

### Step 2: Add SupabaseError import to telegram.py

Check if `SupabaseError` is already imported in `telegram.py`. If not, add:

```python
from hr_breaker.services.supabase import SupabaseError
```

### Step 3: Verify compiles

```
cd C:/Users/aleks/Documents/Projects/hr-breaker && python -m py_compile src/hr_breaker/api/routes/telegram.py && echo OK
```

Expected: `OK`

### Step 4: Commit

```bash
git add src/hr_breaker/api/routes/telegram.py
git commit -m "fix(telegram): handle concurrent profile creation race in /link"
```

---

## Task 4: Fix AuthError escaping except JWTError in verify_jwt

**Files:**
- Modify: `src/hr_breaker/api/auth.py`

**Root cause:** `_get_jwks` and `_get_signing_key` raise `AuthError` (not a subclass of `JWTError`).
In `verify_jwt`, the `except JWTError` handler does not catch `AuthError`, so JWKS network
failures and missing-key errors escape the function without being caught at the JWT layer.
They happen to be caught by `deps.py`'s `except AuthError`, but any future caller of
`verify_jwt` that doesn't also catch `AuthError` will get an unhandled exception.

**Fix:** Add `except AuthError: raise` before `except JWTError` so `AuthError` propagates
cleanly and is explicitly documented as intentional pass-through, not an oversight.

### Step 1: Add explicit AuthError re-raise

In `src/hr_breaker/api/auth.py`, in `verify_jwt`, change:

```python
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise AuthError("Invalid token") from e
```

To:

```python
    except AuthError:
        raise
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise AuthError("Invalid token") from e
```

This makes the contract explicit: `AuthError` (from JWKS fetch / key lookup failures)
propagates as-is; `JWTError` (signature/claims failures) is wrapped in `AuthError`.

### Step 2: Verify compiles

```
cd C:/Users/aleks/Documents/Projects/hr-breaker && python -m py_compile src/hr_breaker/api/auth.py && echo OK
```

Expected: `OK`

### Step 3: Commit

```bash
git add src/hr_breaker/api/auth.py
git commit -m "fix(auth): explicitly re-raise AuthError in verify_jwt so it is not swallowed by JWTError handler"
```

---

## Completion Check

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker
python -m py_compile \
  src/hr_breaker/api/auth.py \
  src/hr_breaker/api/routes/telegram.py \
  src/hr_breaker/api/routes/users.py \
  src/hr_breaker/services/supabase.py && echo "All OK"
```
