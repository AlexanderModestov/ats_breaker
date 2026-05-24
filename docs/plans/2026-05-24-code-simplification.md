# Code Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove duplicated logic, dead code, and debug noise identified in the simplification report.

**Architecture:** Surgical edits only — no behaviour changes. Each task is independent and commits separately. Backend changes first, frontend dead-code deletions after.

**Tech Stack:** Python 3.11 / FastAPI (backend), Next.js 14 / TypeScript (frontend)

---

## Task 1: Remove debug warnings from hot auth path

**Files:**
- Modify: `src/hr_breaker/api/auth.py`

These two `logger.warning` calls fire on every authenticated request, flooding logs with key IDs.

**Step 1: Remove both warning lines**

In `auth.py`, delete lines 41 and 78:

```python
# DELETE this line (line 41 in _get_signing_key):
logger.warning(f"Token kid={kid}, JWKS kids={jwks_kids}")

# DELETE this line (line 78 in verify_jwt):
logger.warning(f"JWT alg={token_alg} kid={unverified_header.get('kid')}")
```

Also remove the now-unused variable `jwks_kids` on the line above the deleted warning (line 40):
```python
# DELETE this line too:
jwks_kids = [k.get("kid") for k in jwks.get("keys", [])]
```

**Step 2: Remove redundant manual expiry check**

`python-jose` already raises `JWTError` on expired tokens. The manual check below is dead code — delete lines 108–113:

```python
# DELETE these lines from verify_jwt:
# Check expiration
exp = payload.get("exp")
if exp:
    exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
    if exp_datetime < datetime.now(tz=timezone.utc):
        raise AuthError("Token has expired")
```

Also remove the now-unused imports at the top of `auth.py`:
```python
# DELETE these two imports:
from datetime import datetime, timezone
```
And remove unused imports `jwk` and `base64url_decode`:
```python
# Change:
from jose import JWTError, jwt, jwk
from jose.utils import base64url_decode
# To:
from jose import JWTError, jwt
```

**Step 3: Verify no tests break**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker
python -m pytest tests/ -x -q 2>/dev/null || echo "no tests found"
```

**Step 4: Commit**

```bash
git add src/hr_breaker/api/auth.py
git commit -m "chore(auth): remove debug warnings and redundant exp check"
```

---

## Task 2: Collapse duplicate bearer-parsing in deps.py

**Files:**
- Modify: `src/hr_breaker/api/deps.py`

`get_current_user` and `get_current_user_email` are identical except the latter also returns the email. Collapse them: `get_current_user` calls `get_current_user_email` and discards the email.

**Step 1: Replace `get_current_user` body**

The current `get_current_user` (lines 48–77) duplicates the bearer parsing from `get_current_user_email` (lines 80–111). Replace the whole function to delegate:

```python
async def get_current_user(
    supabase: Annotated[SupabaseService, Depends(get_supabase_service)],
    authorization: Annotated[str | None, Header()] = None,
    x_bot_api_key: Annotated[str | None, Header()] = None,
    x_telegram_user_id: Annotated[str | None, Header()] = None,
) -> str:
    user_id, _ = await get_current_user_email(
        supabase, authorization, x_bot_api_key, x_telegram_user_id
    )
    return user_id
```

`get_current_user_email` must be defined first in the file (it already is at line 80 — move it above `get_current_user`, or just define `get_current_user` after it).

**Step 2: Reorder functions**

New order in `deps.py`:
1. `get_supabase_service`
2. `_resolve_bot_user`
3. `get_current_user_email`  ← move up (was second)
4. `get_current_user`        ← now just delegates
5. Type aliases (`CurrentUser`, `CurrentUserWithEmail`, `SupabaseServiceDep`)
6. `require_feature`

**Step 3: Verify the app still starts**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker
python -c "from hr_breaker.api.deps import get_current_user, get_current_user_email; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add src/hr_breaker/api/deps.py
git commit -m "refactor(auth): collapse duplicate bearer-parsing in deps"
```

---

## Task 3: Extract _price_id_for_tier helper in StripeService

**Files:**
- Modify: `src/hr_breaker/services/stripe_service.py`

The dict `{"job_hunter": settings.stripe_price_job_hunter, "offer_mode": settings.stripe_price_offer_mode}` is written identically in three methods: `create_checkout_session_for_tier` (line 38), `preview_upgrade` (line 174), `upgrade_subscription` (line 215).

**Step 1: Add the helper method**

Add this method to `StripeService` before `create_checkout_session_for_tier`:

```python
def _price_id_for_tier(self, tier: str) -> str:
    settings = get_settings()
    price_id = {
        "job_hunter": settings.stripe_price_job_hunter,
        "offer_mode": settings.stripe_price_offer_mode,
    }.get(tier)
    if not price_id:
        raise StripeError(f"Unknown tier: {tier}")
    return price_id
```

**Step 2: Replace all three usages**

In `create_checkout_session_for_tier` replace lines 38–43:
```python
# BEFORE:
price_id = {
    "job_hunter": settings.stripe_price_job_hunter,
    "offer_mode": settings.stripe_price_offer_mode,
}.get(tier)
if not price_id:
    raise StripeError(f"Unknown tier: {tier}")

# AFTER:
price_id = self._price_id_for_tier(tier)
```
Also remove the `settings = get_settings()` line that's only used for price lookup in this method (check if it's still needed for other things — it's not, the method only used settings for price_id).

In `preview_upgrade` replace lines 174–178 with:
```python
price_id = self._price_id_for_tier(new_tier)
```
Remove `settings = get_settings()` if only used for price lookup.

In `upgrade_subscription` replace lines 215–219 with:
```python
price_id = self._price_id_for_tier(new_tier)
```
Remove `settings = get_settings()` if only used for price lookup.

**Step 3: Verify import still works**

```bash
python -c "from hr_breaker.services.stripe_service import StripeService; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add src/hr_breaker/services/stripe_service.py
git commit -m "refactor(stripe): extract _price_id_for_tier helper, remove 3× duplication"
```

---

## Task 4: Delete dead frontend components

**Files:**
- Delete: `frontend/src/components/JsonLd.tsx`
- Delete: `frontend/src/components/ProgressStepper.tsx`
- Delete: `frontend/src/components/ThemeSwitcher.tsx`
- Modify: `frontend/src/app/(protected)/settings/page.tsx` (remove commented import/usage)

These three components are never imported anywhere. `components/JsonLd.tsx` is a stale duplicate of `app/components/JsonLd.tsx` with wrong prices (€20 vs €19).

**Step 1: Confirm none are imported**

```bash
grep -r "ProgressStepper\|ThemeSwitcher" C:/Users/aleks/Documents/Projects/hr-breaker/frontend/src --include="*.tsx" --include="*.ts" -l
```

Expected: only the component files themselves (no consumers).

```bash
grep -r "components/JsonLd" C:/Users/aleks/Documents/Projects/hr-breaker/frontend/src --include="*.tsx" -l
```

Expected: only `app/components/JsonLd.tsx` path used in layout, not `components/JsonLd.tsx`.

**Step 2: Delete the three files**

```bash
rm C:/Users/aleks/Documents/Projects/hr-breaker/frontend/src/components/JsonLd.tsx
rm C:/Users/aleks/Documents/Projects/hr-breaker/frontend/src/components/ProgressStepper.tsx
rm C:/Users/aleks/Documents/Projects/hr-breaker/frontend/src/components/ThemeSwitcher.tsx
```

**Step 3: Remove commented ThemeSwitcher usage from settings**

In `frontend/src/app/(protected)/settings/page.tsx`, find and remove:
- The commented `// import { ThemeSwitcher }` line (around line 16)
- The commented `{/* <ThemeSwitcher /> */}` block (around lines 220–230)

**Step 4: TypeScript build check**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 5: Commit**

```bash
git add -u frontend/src/components/JsonLd.tsx frontend/src/components/ProgressStepper.tsx frontend/src/components/ThemeSwitcher.tsx
git add frontend/src/app/(protected)/settings/page.tsx
git commit -m "chore(frontend): delete unused JsonLd, ProgressStepper, ThemeSwitcher components"
```

---

## Task 5: Fix TIER_RANK duplication in pricing page

**Files:**
- Modify: `frontend/src/app/pricing/page.tsx`

`const RANK: Record<Tier, number> = { free: 0, job_hunter: 1, offer_mode: 2 }` is defined inline at line 167, duplicating `TIER_RANK` already exported from `lib/tiers.ts`.

**Step 1: Add import**

At the top of `pricing/page.tsx`, add `TIER_RANK` to the existing import from `lib/tiers` (or add a new import if not already importing from there):

```typescript
import { TIER_RANK } from "@/lib/tiers";
```

**Step 2: Replace inline RANK**

Find the inline definition (line 167):
```typescript
const RANK: Record<Tier, number> = { free: 0, job_hunter: 1, offer_mode: 2 };
```

Replace both references to `RANK` with `TIER_RANK` and delete the const declaration:
```typescript
// BEFORE:
const RANK: Record<Tier, number> = { free: 0, job_hunter: 1, offer_mode: 2 };
if (RANK[planTier] < RANK[current]) {

// AFTER (delete const, change references):
if (TIER_RANK[planTier] < TIER_RANK[current]) {
```

**Step 3: TypeScript build check**

```bash
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

**Step 4: Commit**

```bash
git add frontend/src/app/pricing/page.tsx
git commit -m "refactor(pricing): replace inline RANK with imported TIER_RANK"
```

---

## Completion Check

After all tasks, verify the full build:

```bash
# Backend
cd C:/Users/aleks/Documents/Projects/hr-breaker
python -m py_compile src/hr_breaker/api/auth.py src/hr_breaker/api/deps.py src/hr_breaker/services/stripe_service.py && echo "Backend OK"

# Frontend
cd C:/Users/aleks/Documents/Projects/hr-breaker/frontend
npx tsc --noEmit && echo "Frontend OK"
```
