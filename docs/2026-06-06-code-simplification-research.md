# Code Simplification Research Report

**Date:** 2026-06-06
**Scope:** Full monorepo — Python backend (`src/hr_breaker`), Next.js frontend (`frontend/src`), Telegram bot (`telegram_bot`)
**Status:** Research only. No code changed. Run `/xonovex-workflow:plan-create` to turn selected items into an implementation plan.

> **Verification note:** Every dead-code claim below was grep-verified across the repo. Four "dead code" candidates surfaced by the automated scan were **false positives** and have been removed (see *Rejected findings* at the end). Trust the severities here over a raw scan.

---

## Top-line summary

| Category | Items | Highest value |
|---|---|---|
| Duplicates / consolidation | 11 | **optimizer.py vs optimizer_v2.py** (~95% identical, both live) |
| Dead code | 3 (verified) | Unused `motion.tsx` wrappers |
| Repeated patterns → shared helper | 6 | Supabase error handling, profile/run lookup, API-client error mapping |
| Over-engineering | 2 | `CVDropdown` DOM manipulation |
| Types | 2 | Unused `CoachChatRequest` / `CoachSSEEvent` |
| Config | 3 | Route-local schemas, list-parsers |

Realistic impact if all HIGH+MEDIUM items are done: **~350–450 lines removed**, no behavior change.

---

## HIGH PRIORITY

### H1 — Consolidate `optimizer.py` and `optimizer_v2.py` (~95% duplicated)
- **Files:** `src/hr_breaker/agents/optimizer.py` (lines 27–292), `src/hr_breaker/agents/optimizer_v2.py` (lines 28–298)
- **Verified:** BOTH are live. `orchestration.py:158-162` selects between `optimize_resume` (v1) and `optimize_resume_v2` (v2) at runtime. This is **duplication, not dead code** — do not delete v1.
- **What's duplicated:** `_load_resume_guide()`, the four agent tools (`check_content_length`, `preview_resume`, `check_keywords_tool`, `validate_structure`), the `_length_cache` logic, agent setup, and most of the `optimize_resume*` body. The only real differences are the system prompt, the result model, and the "how to fix filters" text.
- **Recommendation:** Extract a single parameterized factory — `get_optimizer_agent(version, job, source)` — with the prompt / result-model / fix-text injected as parameters. Keep the two public entrypoints as thin wrappers so `orchestration.py` is untouched. Eliminates ~200 lines.

### H2 — Shared Supabase error → HTTP 500 handling (7+ sites)
- **Files:** `routes/cvs.py:56,132,147`, `routes/optimize.py:304,367,394`, `routes/users.py:44,96`
- **Pattern:** `except SupabaseError as e: raise HTTPException(500, str(e)) from e` repeated verbatim.
- **Recommendation:** Register a single FastAPI exception handler for `SupabaseError` in `api/main.py` (cleanest — removes every local `try/except`), or a `handle_supabase_error()` helper in `deps.py`.

### H3 — Shared "fetch profile or 404" dependency (11+ sites)
- **Files:** `deps.py:120`, `users.py:37`, `optimize.py:259`, `subscription.py:66`, `coach.py:121`, `feedback.py:73`, …
- **Pattern:** `profile = supabase.get_profile(user_id)` + null check + 404.
- **Recommendation:** A FastAPI dependency `get_user_profile(...) -> dict` that returns the profile or raises 404. Inject where needed.

### H4 — Shared "fetch optimization run + verify owner or 404" helper (6+ sites)
- **Files:** `optimize.py:314`, `editor.py:47`, `coach.py:122,177,187`
- **Recommendation:** `get_user_optimization_run(run_id, user_id, supabase) -> dict` in `deps.py`.

### H5 — Response-object construction helpers (DRY route responses)
- `_profile_to_schema(profile)` → `users.py:46-53` & `87-94` (identical)
- `_cv_to_response(cv, include_text=False)` → `cvs.py:46,70,123` (3×)
- `_run_to_status(run)` → `optimize.py:322,435` (2×)
- **Recommendation:** One small builder per response model; call from each handler.

### H6 — Telegram API-client error mapping (8+ sites)
- **File:** `telegram_bot/bot/services/api_client.py`
- **Pattern:** identical `HTTPStatusError`/`RequestError` → `BackendError` try/except around every request.
- **Recommendation:** A private `_request(method, path, **kw)` wrapper that centralizes the error mapping; each public method calls it.

---

## MEDIUM PRIORITY

### M1 — Remove verified-dead `motion.tsx` wrappers
- **File:** `frontend/src/components/motion.tsx`
- **Verified dead (definitions only, zero usages):** `PageTransition` (87), `FadeIn` (153), `HoverScale` (192), `Skeleton` (210).
- **Recommendation:** Delete these four exported components (~60 LOC). Keep `StaggerList`, `StaggerItem`, `SlideUp`, `fadeSlideUp`, which are used.

### M2 — Keyboard handler hook (Enter/Escape) (3 sites)
- **Files:** `EditPopup.tsx:26-31`, `InlineEdit.tsx:35-42`, `coach/ThreadListItem.tsx:37-42`
- **Recommendation:** `useFormKeyboard({ onSave, onCancel })` custom hook.

### M3 — Blob-download logic duplicated (2 sites)
- **Files:** `hooks/useOptimization.ts:134-150` (`useDownloadPDF`), `results/[id]/edit/page.tsx:130-145` (`handleDownload`)
- **Recommendation:** Generic `useDownloadBlob()` (or `downloadBlob(blob, filename)` util) reused in both.

### M4 — Coach trial/lock status duplicated (2 sites)
- **Files:** `coach/CoachSidebar.tsx:36-37`, `coach/AddPositionDialog.tsx:26-27`
- **Pattern:** `isTrialUser = sub?.coach != null && !sub.coach.is_unlimited`; `lockedCompany = sub?.coach?.locked_company ?? null`.
- **Recommendation:** `useCoachTrialStatus()` returning `{ isTrialUser, lockedCompany, isPositionLocked }`.

### M5 — `CVDropdown` uses DOM manipulation instead of React state
- **File:** `frontend/src/components/CVDropdown.tsx:20-57`
- **Issue:** `classList.toggle()` / `querySelector()` for open/close — fragile, hard to test.
- **Recommendation:** Controlled `useState` for `isOpen` (existing UI primitives already available).

### M6 — Move route-local Pydantic schemas into `schemas.py`
- **Files:** `routes/telegram.py:26-37`, `routes/feedback.py:25-38`, `routes/subscription.py:20-55`, `routes/editor.py:21-126`
- **Recommendation:** Centralize request/response models for consistency and reuse.

### M7 — Telegram bot duplicates main `config.py` fields
- **Files:** `src/hr_breaker/config.py` vs `telegram_bot/bot/config.py:10-29`
- **Note:** The bot is a separate deployable (own `pyproject.toml`), so full sharing may be intentional. **Confirm deployment coupling before acting** — if they ship together, import shared settings; if independent, leave as-is.

### M8 — Missing-PDF-text FilterResult duplicated (2 sites)
- **Files:** `filters/keyword_matcher.py:107-115`, `filters/vector_similarity_matcher.py:53-61`
- **Recommendation:** `_missing_pdf_text_result(name, threshold)` helper in `filters/base.py`.

### M9 — Per-filter `threshold` property boilerplate (4+ sites)
- **Files:** `keyword_matcher.py:99`, `llm_checker.py:16`, `vector_similarity_matcher.py:24`, `content_integrity_checker.py:16`
- **Recommendation:** Default `threshold` property on `BaseFilter` reading a `_threshold`/settings key; override only when dynamic.

---

## LOW PRIORITY

### L1 — Unused alias export `edit_resume_html`
- **File:** `src/hr_breaker/agents/__init__.py:7,18`
- **Verified:** `edit_resume` itself IS used (`routes/editor.py:12` imports it directly from `resume_editor`). The **aliased re-export** `edit_resume_html` in `__all__` has no importers. Safe to drop the alias (keep `edit_resume`).

### L2 — Unused TS types
- **File:** `frontend/src/types/index.ts:167-171` (`CoachChatRequest`), `173-177` (`CoachSSEEvent`)
- **Verified:** no importers. Remove, or add a comment if kept as a documented API contract.

### L3 — `Theme` type alias not reused
- **File:** `frontend/src/types/index.ts` — literal `"minimal" | "professional" | "bold"` repeated in `UserProfile`/`UserProfileUpdate` instead of using the existing `Theme` alias.

### L4 — Generic list-parser in config
- **File:** `src/hr_breaker/config.py:118-129` — `_parse_cors_origins` and `_parse_unlimited_users` are the same logic. One `_parse_list(value, transform=str.strip)` covers both.

### L5 — Date / display-URL formatting inline duplicates
- Date `MMM D`: `CVCard.tsx:23-27`, `OptimizationCard.tsx:86-89` → `formatDateShort()` in `lib/utils.ts`.
- URL hostname: `OptimizationCard.tsx:91-99`, `ResumePreview.tsx:173-183` → `getDisplayUrl()` in `lib/utils.ts`.

### L6 — `checkout = useCheckout()` possibly unused result
- **File:** `coach/CoachSidebar.tsx:38` — hook is called but verify the `checkout` value is actually used in that file (pricing is opened via `usePricingModal`). If unused, drop the call. **Verify before removing.**

### L7 — Telegram bot exception subclasses
- **File:** `telegram_bot/bot/services/api_client.py:11-24` — `QuotaExceededError`/`JobUnavailableError`/`BackendError` add no specialized behavior. Optional: collapse, or keep if used for distinct `except` branches (check call sites first).

---

## Rejected findings (false positives from the automated scan — do NOT action)

1. **`renderer.render_data()` "dead"** — FALSE. Live at `orchestration.py:213` and `combined_reviewer.py:191`. It is in fact a primary render path.
2. **`BaseRenderer` "dead"** — FALSE. It's the base of `HTMLRenderer` and is exported/consumed via `services/__init__.py`. (At most a *single-impl ABC* style nit, not dead code — leave it.)
3. **`coach.py` / `create_coach_agent()` "dead"** — FALSE. Used at `api/routes/coach.py:216`.
4. **`optimizer.py` "dead / superseded by v2"** — FALSE. Selected at runtime in `orchestration.py:158-162`. It's a duplication target (H1), not removable.

---

## Suggested sequencing for plan-create

1. **Pure deletes (lowest risk):** M1, L1, L2 → run typecheck/lint.
2. **Backend helper extractions:** H2 → H3 → H4 → H5 → H6, validating after each.
3. **Optimizer consolidation (H1):** highest payoff, do as its own focused change with the optimizer flow exercised end-to-end.
4. **Frontend hooks/utils:** M2, M3, M4, M5, L5.
5. **Config/organization:** M6, M8, M9, L4 (treat M7 only after confirming bot deployment coupling).
