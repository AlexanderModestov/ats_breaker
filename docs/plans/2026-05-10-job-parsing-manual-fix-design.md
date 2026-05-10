# Manual Fix for Job Title/Company After Parsing — Design

**Date:** 2026-05-10
**Status:** Approved, ready for implementation plan

## Problem

The job parser sometimes fails to extract `title` and/or `company` correctly. Currently:

- When the LLM-extracted `company` is not grounded in the posting text and no URL fallback exists, it becomes `"Not Specified"`.
- When the LLM-extracted `title` fails the grounding check, the value is kept as-is (potentially fabricated) — only a log warning is raised.

These values are used by:

- `optimizer.py:223-224` and `combined_reviewer.py:238-239` — directly in LLM prompts (affects optimization quality).
- Results page header and history list — displayed to user.

The user dislikes seeing `"Not Specified"` and other garbage labels in the UI/history.

## Goals

- Allow the user to fix `title` and `company` **after** optimization completes.
- No additional confirmation step **before** optimization (keeps the happy path seamless).
- Fix is cosmetic only — does not re-run optimization.
- Edit affordance shows **only when the parser actually failed** for that field.

## Non-goals

- Re-running the optimizer with corrected values.
- Editing other parsed fields (location, requirements, etc.).
- Editing on the history list page directly (history reads the same `job_parsed`, so corrected values appear automatically).
- Pre-optimization preview/confirmation UI.

## Detection rules

Two fields, two rules:

| Field   | needs_review when …                                                                 |
|---------|--------------------------------------------------------------------------------------|
| company | Final value equals `"Not Specified"` (i.e. neither LLM nor URL fallback succeeded). |
| title   | `_is_grounded(job.title, text)` returned `False` (LLM hallucinated a title).        |

The "URL corrected the LLM" case (LLM extracted some grounded value, URL disagreed, URL won) is **not** flagged — we trust URL slugs from ATS systems.

## Backend

### `parse_job_posting` signature

Change return from `JobPosting` to `tuple[JobPosting, list[str]]`. The list contains field names needing review (`["title"]`, `["company"]`, or both).

`JobPosting` model itself stays unchanged — keeps it clean for LLM `output_type` and avoids leaking metadata into downstream consumers.

Single existing call site (`optimize.py:86`) updated.

### Persistence

In `_run_optimization` (`optimize.py:90-103`), include the list inside `job_parsed`:

```python
job_parsed = {
    "title": job.title,
    "company": job.company,
    ...
    "needs_review": needs_review,  # ["title", "company"] or subset
}
```

`OptimizationStatus` schema doesn't need changes — `job_parsed: dict[str, Any]` already passes everything through.

### Edit endpoint

```
PATCH /api/optimize/{run_id}/job
Body: { "title"?: string, "company"?: string }
Response: OptimizationStatus (updated)
```

Behavior:

- Auth: same `CurrentUser` dependency, same ownership check as other routes.
- Reject if `run["status"]` is `pending` or `parse_job` (parsing still in flight).
- For each provided field: validate non-empty after trim, ≤200 chars, then update inside `job_parsed`.
- Remove the corresponding entry from `job_parsed["needs_review"]`.
- Persist via existing `supabase.update_optimization_run(run_id, {"job_parsed": ...})`.

New schema `JobPatchRequest` in `schemas.py`.

## Frontend

### Results page (`results/[id]/page.tsx`)

Block at lines 156-187 (job info header) gets two changes:

- **Title (`<h1>`)**: when `"title" in job_parsed.needs_review`, render a clickable placeholder ("Название не определено — указать") with a pencil icon instead of the raw `job_parsed.title`.
- **Company line**: same treatment when `"company" in job_parsed.needs_review`.

Click → opens `EditPopup` (existing component) with a single text input. Save → calls PATCH endpoint → invalidates `useOptimizationStatus` query → re-render replaces the placeholder with the entered value as static text.

### Hook

New `useUpdateOptimizationJob` in `hooks/useOptimization.ts` — wraps `apiFetch("PATCH", ...)`, invalidates `["optimization", runId]` on success.

### History page

No changes required. It reads the same `job_parsed` shape; corrected values surface automatically once the user fixes them on the results page.

## Out of scope (not changing)

- `JobPosting` model.
- Optimizer / reviewer prompts and logic.
- PDF filename (`resume_{run_id}.pdf` — independent of title/company).
- CLI flow (already prompts interactively for `Not Specified`).

## Rollout

- DB schema: no changes (job_parsed is JSONB).
- Backwards compatibility: old runs without `needs_review` in `job_parsed` → frontend treats missing key as empty list → no edit affordance shown. Acceptable; only new runs get the feature.

## Test plan

Backend:

- Parser returns expected `needs_review` list across cases: title not grounded, company falls back to Not Specified, both, neither, URL correction (no flag).
- PATCH endpoint: auth, ownership, status guard, field validation, partial updates, `needs_review` cleanup.

Frontend:

- Results page: pencil shown only for fields in `needs_review`; popup opens, saves, refreshes.
- Old runs (no `needs_review` key) render as before.
