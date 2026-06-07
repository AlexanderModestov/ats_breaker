# Code Simplification Research — Python Backend

**Date:** 2026-06-07
**Scope:** `src/hr_breaker/` only (Python backend; ~7,800 LOC). Frontend / Telegram bot excluded.
**Status:** Research only. No code changed. Run `/xonovex-workflow:plan-create` to turn selected items into an implementation plan.

> **Relationship to the prior report** (`docs/2026-06-06-code-simplification-research.md`, cross-stack): this report **re-verifies the backend items** of that report against current `dev` and adds **new backend-only findings**. All claims grep-verified across the whole repo (incl. `tests/`, `telegram_bot/`, `cli.py`, dynamic dispatch / decorators).

---

## What the recent API refactor already fixed

Commit `6b1df8f "refactor(api): centralize Supabase errors and dedupe route helpers"` **resolved** four of the prior report's HIGH items — do **not** re-action them:

| Prior item | Status | Evidence |
|---|---|---|
| H2 Supabase error → HTTP 500 | ✅ Resolved | global handler at `api/main.py:59-62`; local `try/except SupabaseError` removed |
| H3 fetch-profile-or-404 | ✅ Resolved | `get_profile_or_404()` in `api/deps.py:19-24`, used across routes |
| H4 fetch-run-or-404 | ✅ Resolved | `get_run_or_404()` in `api/deps.py:27-32`, used in coach/optimize/editor |
| H5 response builders | ✅ Resolved | `_profile_to_schema` / `_cv_to_response` / `_run_to_status` extracted |
| L1 `edit_resume_html` alias | ✅ Cleared | alias removed from `agents/__init__.py` |

---

## Top-line summary (still-actionable, backend)

| Category | Highest value | Est. LOC |
|---|---|---|
| Duplicates | **H1** optimizer.py vs optimizer_v2.py (~95% identical, both live) | ~200 |
| Filter boilerplate | F1–F3 FilterResult / threshold / missing-pdf-text | ~70–100 |
| Config / env hygiene | C1–C3 scattered `os.getenv` + import-time `os.environ` mutation | ~30 |
| Route patterns | R1–R4 profile/cv/run/job helpers | ~25 |
| Organization | route-local schemas → `schemas.py` | ~35 |
| Dead deps | `watchdog` unused | — |

Realistic impact if all HIGH+MEDIUM done: **~370–420 lines removed**, no behavior change (one exception: C3 changes import-time side-effect — a fix, see note).

---

## HIGH PRIORITY

### H1 — Consolidate `optimizer.py` and `optimizer_v2.py` (~95% duplicated) — *carried, still valid*
- **Files:** `agents/optimizer.py` (~27–292), `agents/optimizer_v2.py` (~28–298). **Both live** — `orchestration.py:162-165` selects v1/v2 at runtime; not dead code.
- **Duplicated:** `_load_resume_guide()`, the four agent tools (`check_content_length`, `preview_resume`, `check_keywords_tool`, `validate_structure`), `_length_cache`, agent setup, most of `optimize_resume*`. Only the system prompt, result model, and "how to fix filters" text differ.
- **Recommendation:** Extract a parameterized factory `get_optimizer_agent(version, job, source)` with prompt / result-model / fix-text injected; keep the two public entrypoints as thin wrappers so `orchestration.py` is untouched. **~200 LOC.** Highest payoff; do as its own focused change with the optimizer flow exercised end-to-end.

---

## MEDIUM PRIORITY

### Filters

**F1 — Missing-PDF-text `FilterResult` duplicated** *(prior M8, still present)*
- **Files:** `filters/keyword_matcher.py:107-115`, `filters/vector_similarity_matcher.py:53-61` — byte-identical `FilterResult(passed=False, score=0.0, …, issues=["No PDF text available"], …)`.
- **Recommendation:** `_missing_pdf_text_result(filter_name, threshold)` helper in `filters/base.py`. (The "dependency unavailable" block at `vector_similarity_matcher.py:44-50` is the same shape — fold in.) ~15 LOC.

**F2 — Per-filter `threshold` property boilerplate** *(prior M9, still present)*
- **Files:** `keyword_matcher.py:98-99`, `llm_checker.py:15-17`, `vector_similarity_matcher.py:23-25`, `content_integrity_checker.py:15-17` — each repeats `@property def threshold: return get_settings().filter_<x>_threshold`.
- **Recommendation:** Default `threshold` property on `BaseFilter` keyed by a per-subclass `_threshold_key`; override only when dynamic. ~12 LOC.

**F3 — `FilterResult` construction boilerplate (factory)** *(new)*
- **Files:** `content_length.py` (4×), `keyword_matcher.py` (2×), `vector_similarity_matcher.py` (2×), plus `content_integrity_checker.py`, `llm_checker.py`, `data_validator.py` — every result repeats `filter_name=self.name, threshold=self.threshold`.
- **Recommendation:** `BaseFilter.pass_result(...)` / `fail_result(issues, suggestions)` (or `FilterResult.passed_for(filter)` classmethods). ~50–80 LOC.
- **Judgment note:** F1–F3 overlap; the cleanest single change is a small `BaseFilter` result-builder + default threshold that subsumes all three. This *adds* a base-class abstraction — justified here because there are 7 filter subclasses, but keep it minimal (no config beyond what's used).

### Route patterns (complement the already-extracted helpers)

**R1 — `get_profile(user_id) or {}` repeated (7 sites)** *(new)*
- **Files:** `routes/coach.py:121,174`, `routes/feedback.py:73`, `routes/subscription.py:101,127,148,175`.
- **Note:** distinct from `get_profile_or_404()` — these legitimately tolerate a missing profile.
- **Recommendation:** `get_profile_or_empty()` dependency in `deps.py` (mirrors the existing 404 variant). ~14 LOC.

**R2 — CV-text fetch with empty fallback (2–3 sites)** *(new)*
- **Files:** `routes/coach.py:189-192`, `routes/editor.py:85-88` — `cv = get_cv(...); cv_text = cv.get("content_text","") or ""`.
- **Recommendation:** `get_cv_text(supabase, cv_id, user_id) -> str` helper. ~6 LOC.

**R3 — `_get_completed_run()` is route-local** *(new)*
- **File:** `routes/editor.py:47-54` — fetch run + assert completed; close cousin of `get_run_or_404`.
- **Recommendation:** Promote to `deps.py` as `get_completed_run(run_id, user_id, supabase)`. ~8 LOC.

**R4 — `JobPosting.model_validate(run["job_parsed"])` repeated** *(new)*
- **File:** `routes/editor.py:66,108`.
- **Recommendation:** `_job_from_run(run) -> JobPosting` (local to editor.py is fine). ~2 LOC.

### Config / env hygiene *(new)*

**C1 — GCP credentials env access in `api/main.py:35-42`**
- Reads `GOOGLE_APPLICATION_CREDENTIALS_JSON` / `GOOGLE_APPLICATION_CREDENTIALS` and mutates `os.environ` directly, outside `config.py`.
- **Recommendation:** Move the read into `config.py` (a `Settings` field + a small setup helper); call from the lifespan. ~10 LOC.

**C2 — PostHog env access in `analytics.py:17-18`**
- Direct `os.getenv("POSTHOG_API_KEY"/"POSTHOG_HOST")` instead of `Settings`.
- **Recommendation:** Add `posthog_api_key` / `posthog_host` to `Settings`. ~4 LOC.

**C3 — `renderer.py` mutates `os.environ` at import time (`:22,34`)**
- `_setup_macos_library_path()` sets `DYLD_FALLBACK_LIBRARY_PATH` on module import (an import-time global side effect).
- **Recommendation:** Move into the FastAPI lifespan (alongside C1) or guard so it runs once. ⚠️ This is the one item that **changes behavior** (when the env var is set) — it's a fix, validate rendering still works on macOS.

**Also:** **L4** *(carried, holds)* — `config.py:118-129` `_parse_cors_origins` and `_parse_unlimited_users` are the same logic → one `_parse_list(value, transform=str.strip)`. ~10 LOC.

### Organization

**O1 — Route-local Pydantic schemas → `schemas.py`** *(prior M6, still present)*
- **Files:** `routes/editor.py:21-126` (6 models), `routes/subscription.py:20-55` (5), `routes/telegram.py:26-37` (3), `routes/feedback.py:25-38` (2).
- **Recommendation:** Centralize in `api/schemas.py` (as already done for the main models).
- **Judgment note:** organizational, not a complexity reduction — value is discoverability/consistency. Lower priority than the dedup items.

**O2 — `TEMPLATE_DIR` duplicated across 3 agent modules** *(new)*
- **Files:** `agents/coach.py:13`, `agents/optimizer.py:24`, `agents/optimizer_v2.py:25` — identical `Path(__file__).parent.parent.parent.parent / "templates"`.
- **Recommendation:** One constant in `agents/__init__.py` (or a shared module), imported by all three. Naturally folds into H1. ~6 LOC.

---

## LOW PRIORITY

- **Dead dependency:** `watchdog>=6.0.0` in `pyproject.toml:31` — **0 usages** repo-wide. Safe to remove. (Note: `python-multipart`, `uvicorn` look unused by grep but are real runtime/peer deps for FastAPI form uploads / ASGI — **keep**.)
- **L7 — Scattered route constants:** `RATE_LIMIT_WINDOW`/`RATE_LIMIT_MAX`/`FEEDBACK_TABLE` (`routes/feedback.py:20-22`), `INIT_DATA_MAX_AGE_SECONDS`/`WELCOME_AFTER_LINK_TEXT` (`routes/telegram.py`). Optional `api/constants.py`; low coupling, low urgency.
- **N7 — `_extract_job_url()`** (`optimize.py:39-42`): single-route helper; **keep local** (not worth moving until a second caller appears).

---

## Verified acceptable / do NOT action

- **Dead-code false positives** (from prior report, re-confirmed live): `renderer.render_data()`, `BaseRenderer` (single-impl ABC, but on the export path — fine), `coach.create_coach_agent()`, `optimizer.py` (runtime-selected), `FilterRegistry.names()` (used by tests), `PDFStorage.save_record()` (no-op by design, used by CLI).
- No functions with >5 custom params; no inheritance chains >3 levels. FastAPI dependency params are an accepted pattern, not over-engineering.

---

## Suggested sequencing for plan-create

1. **Pure deletes (lowest risk):** remove `watchdog` dep; **L4** list-parser; **O2** TEMPLATE_DIR → typecheck/lint.
2. **Filter cleanup:** **F1 + F2 + F3** as one focused `BaseFilter` change → run `tests/test_filters.py`, `test_data_validator.py`.
3. **Route helpers:** **R1 → R2 → R3 → R4** in `deps.py`/editor → run route tests after each.
4. **Config/env:** **C1 + C2 + C3** (lifespan) → verify startup + rendering (C3 is the only behavior change).
5. **Organization:** **O1** schema move (optional, taste).
6. **High payoff, isolated:** **H1** optimizer consolidation → full optimizer end-to-end + orchestration tests.
