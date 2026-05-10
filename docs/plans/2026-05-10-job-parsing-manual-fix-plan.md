# Manual Fix for Job Title/Company — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to manually correct `title`/`company` after parsing fails, via an inline pencil-edit on the results page.

**Architecture:** Parser surfaces a `needs_review` list of fields where extraction failed. The list is persisted alongside other parsed fields inside `job_parsed` (a JSONB column). A new `PATCH /api/optimize/{run_id}/job` endpoint updates `title`/`company` and clears the corresponding `needs_review` entry. The results page renders a pencil-edit affordance only for fields in `needs_review`; other surfaces (history) read the same field automatically.

**Tech Stack:** FastAPI + Pydantic v2, pytest, Next.js 15 (App Router), TanStack Query, existing `EditPopup` component.

**Companion design:** `docs/plans/2026-05-10-job-parsing-manual-fix-design.md`

---

## Backend

### Task 1: Parser returns `needs_review`

**Files:**
- Modify: `src/hr_breaker/agents/job_parser.py:118-150`
- Modify: `tests/test_job_parser.py:127-194`

**Step 1: Add a failing test for the new return shape**

Append to `tests/test_job_parser.py` inside `TestParseJobPostingMerge`:

```python
async def test_returns_empty_needs_review_when_all_grounded(self):
    llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
    text = "Podcastle is hiring a Backend Eng."
    with patch(
        "hr_breaker.agents.job_parser.get_job_parser_agent",
        return_value=_mock_agent_returning(llm_job),
    ):
        job, needs_review = await parse_job_posting(text)
    assert needs_review == []

async def test_needs_review_contains_company_when_not_specified(self):
    llm_job = JobPosting(title="Backend Eng", company="Microsoft")
    text = "Acme is hiring a Backend Eng."  # company not grounded, no URL
    with patch(
        "hr_breaker.agents.job_parser.get_job_parser_agent",
        return_value=_mock_agent_returning(llm_job),
    ):
        job, needs_review = await parse_job_posting(text)
    assert job.company == COMPANY_NOT_SPECIFIED
    assert "company" in needs_review

async def test_needs_review_omits_company_when_url_filled(self):
    # LLM ungrounded but URL provided a fallback → final company is fine
    llm_job = JobPosting(title="Backend Eng", company="Microsoft")
    text = "Looking for a Backend Eng."
    with patch(
        "hr_breaker.agents.job_parser.get_job_parser_agent",
        return_value=_mock_agent_returning(llm_job),
    ):
        job, needs_review = await parse_job_posting(
            text, url="https://podcastle.bamboohr.com/careers/56"
        )
    assert job.company == "podcastle"
    assert "company" not in needs_review

async def test_needs_review_contains_title_when_ungrounded(self):
    llm_job = JobPosting(title="Fabricated Title", company="Podcastle Inc.")
    text = "Podcastle is hiring."  # title not in text
    with patch(
        "hr_breaker.agents.job_parser.get_job_parser_agent",
        return_value=_mock_agent_returning(llm_job),
    ):
        job, needs_review = await parse_job_posting(text)
    assert "title" in needs_review
```

Also update each existing test in `TestParseJobPostingMerge` to unpack the tuple — change `job = await parse_job_posting(...)` to `job, _ = await parse_job_posting(...)`. Six call sites at lines ~136, 146, 156, 168, 180, 192.

**Step 2: Run tests to verify they fail**

```
pytest tests/test_job_parser.py::TestParseJobPostingMerge -v
```

Expected: New tests fail with `TypeError: cannot unpack non-iterable JobPosting`.

**Step 3: Update the implementation**

Replace `src/hr_breaker/agents/job_parser.py:118-150` with:

```python
async def parse_job_posting(
    text: str, url: str | None = None
) -> tuple[JobPosting, list[str]]:
    """Parse job posting text into structured data.

    Returns the parsed JobPosting along with a list of field names whose
    extraction failed and are recommended for manual review:
      - "company" when the final value is COMPANY_NOT_SPECIFIED
      - "title" when the LLM-extracted title is not grounded in the text
    """
    agent = get_job_parser_agent()
    result = await agent.run(f"Parse this job posting:\n\n{text}")
    job = result.output

    url_company = extract_company_from_url(url) if url else None
    warnings: list[str] = []
    needs_review: list[str] = []

    if _is_grounded(job.company, text, is_company=True):
        if url_company and not _company_matches(job.company, url_company):
            warnings.append(
                f"URL says '{url_company}' but LLM extracted '{job.company}' — trusting URL"
            )
            job.company = url_company
    else:
        warnings.append(f"company '{job.company}' not found in posting text")
        job.company = url_company or COMPANY_NOT_SPECIFIED

    if job.company == COMPANY_NOT_SPECIFIED:
        needs_review.append("company")

    if not _is_grounded(job.title, text):
        warnings.append(f"title '{job.title}' not found in posting text")
        needs_review.append("title")

    if warnings:
        logger.warning("Job parser grounding issues: %s", "; ".join(warnings))

    job.raw_text = text
    return job, needs_review
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_job_parser.py -v
```

Expected: All `TestParseJobPostingMerge` tests pass, including the four new ones.

**Step 5: Commit**

```
git add src/hr_breaker/agents/job_parser.py tests/test_job_parser.py
git commit -m "feat(parser): return needs_review list alongside parsed JobPosting"
```

---

### Task 2: Persist `needs_review` in `job_parsed`

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py:86-103`

**Step 1: Update the call site**

In `_run_optimization`, change line 86 and the `job_parsed` dict (lines 90-97):

```python
        # Parse job posting
        parse_start = time.perf_counter()
        print(f"📋 Parsing job posting...")
        job, needs_review = await parse_job_posting(job_text, url=job_url)
        timing["parse_job"] = time.perf_counter() - parse_start
        print(f"⏱️  Parse job: {timing['parse_job']:.2f}s - {job.title} at {job.company}")
        logger.info(f"[{run_id}] Job parsed: {job.title} at {job.company}")
        job_parsed = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "requirements": job.requirements,
            "responsibilities": job.responsibilities,
            "keywords": job.keywords,
            "needs_review": needs_review,
        }
```

No other call sites use `parse_job_posting` (verified via grep — CLI doesn't import it; it has its own flow).

**Step 2: Verify nothing else broke**

```
pytest tests/ -v -x
```

Expected: All tests pass. (The route isn't covered by unit tests today; we'll add coverage in Task 3 for the new endpoint.)

**Step 3: Commit**

```
git add src/hr_breaker/api/routes/optimize.py
git commit -m "feat(optimize): persist parser needs_review inside job_parsed"
```

---

### Task 3: PATCH endpoint to update title/company

**Files:**
- Modify: `src/hr_breaker/api/schemas.py` (add new schema)
- Modify: `src/hr_breaker/api/routes/optimize.py` (add new route)
- Create: `tests/test_optimize_routes.py`

**Step 1: Write failing tests**

Create `tests/test_optimize_routes.py`:

```python
"""Tests for /api/optimize PATCH route (manual title/company fix)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from hr_breaker.api.deps import get_current_user, get_supabase_service
from hr_breaker.api.main import app

USER = "user-uuid"
RUN_ID = "run-uuid"


def _run(status: str = "complete", needs_review: list[str] | None = None) -> dict:
    return {
        "id": RUN_ID,
        "user_id": USER,
        "status": status,
        "job_parsed": {
            "title": "Original Title",
            "company": "Not Specified",
            "location": "Remote",
            "requirements": [],
            "responsibilities": [],
            "keywords": [],
            "needs_review": needs_review if needs_review is not None else ["company"],
        },
        "created_at": "2026-05-10T00:00:00+00:00",
        "iterations": 1,
        "current_step": None,
        "feedback": None,
        "result_html": None,
        "error": None,
        "timing": None,
        "first_name": None,
        "last_name": None,
    }


@pytest.fixture
def fake_supabase():
    svc = MagicMock()
    svc.get_optimization_run.return_value = _run()
    svc.update_optimization_run.return_value = None
    return svc


@pytest.fixture
def client(fake_supabase):
    app.dependency_overrides[get_supabase_service] = lambda: fake_supabase
    app.dependency_overrides[get_current_user] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_patch_updates_company_and_clears_needs_review(client, fake_supabase):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme Corp"},
    )
    assert resp.status_code == 200
    update_call = fake_supabase.update_optimization_run.call_args
    run_id_arg, payload = update_call[0]
    assert run_id_arg == RUN_ID
    assert payload["job_parsed"]["company"] == "Acme Corp"
    assert payload["job_parsed"]["title"] == "Original Title"  # unchanged
    assert "company" not in payload["job_parsed"]["needs_review"]


def test_patch_updates_both_fields(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = _run(
        needs_review=["title", "company"]
    )
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"title": "Senior Eng", "company": "Acme"},
    )
    assert resp.status_code == 200
    payload = fake_supabase.update_optimization_run.call_args[0][1]
    assert payload["job_parsed"]["title"] == "Senior Eng"
    assert payload["job_parsed"]["company"] == "Acme"
    assert payload["job_parsed"]["needs_review"] == []


def test_patch_strips_whitespace(client, fake_supabase):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "  Acme  "},
    )
    assert resp.status_code == 200
    payload = fake_supabase.update_optimization_run.call_args[0][1]
    assert payload["job_parsed"]["company"] == "Acme"


def test_patch_rejects_empty_company(client):
    resp = client.patch(f"/api/optimize/{RUN_ID}/job", json={"company": "   "})
    assert resp.status_code == 422


def test_patch_rejects_too_long(client):
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"title": "x" * 201},
    )
    assert resp.status_code == 422


def test_patch_requires_at_least_one_field(client):
    resp = client.patch(f"/api/optimize/{RUN_ID}/job", json={})
    assert resp.status_code == 422


def test_patch_404_when_run_missing(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = None
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme"},
    )
    assert resp.status_code == 404


def test_patch_blocked_while_parsing(client, fake_supabase):
    fake_supabase.get_optimization_run.return_value = _run(status="parse_job")
    resp = client.patch(
        f"/api/optimize/{RUN_ID}/job",
        json={"company": "Acme"},
    )
    assert resp.status_code == 409


def test_patch_unauthenticated_returns_401():
    app.dependency_overrides.clear()
    c = TestClient(app)
    resp = c.patch(f"/api/optimize/{RUN_ID}/job", json={"company": "Acme"})
    assert resp.status_code == 401
```

**Step 2: Run to verify they fail**

```
pytest tests/test_optimize_routes.py -v
```

Expected: All tests fail with 404 or 405 (route doesn't exist).

**Step 3: Add the schema**

Append to `src/hr_breaker/api/schemas.py` (alongside the other Optimization schemas):

```python
class JobPatchRequest(BaseModel):
    """Update title/company of a parsed job. At least one field required."""

    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _at_least_one_and_nonempty(self):
        if self.title is None and self.company is None:
            raise ValueError("Provide at least one of title or company")
        for name in ("title", "company"):
            value = getattr(self, name)
            if value is not None:
                stripped = value.strip()
                if not stripped:
                    raise ValueError(f"{name} must be non-empty")
                setattr(self, name, stripped)
        return self
```

**Step 4: Add the route**

Append to `src/hr_breaker/api/routes/optimize.py` (after the DELETE handler, before EOF):

```python
@router.patch("/{run_id}/job", response_model=OptimizationStatus)
async def update_optimization_job(
    run_id: str,
    request: JobPatchRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationStatus:
    """Manually fix parsed title/company when the parser failed.

    Updates only labels in `job_parsed` — does not re-run optimization.
    """
    run = supabase.get_optimization_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    if run["status"] in ("pending", "parse_job"):
        raise HTTPException(
            status_code=409, detail="Job is still being parsed; try again shortly"
        )

    job_parsed = dict(run.get("job_parsed") or {})
    needs_review = list(job_parsed.get("needs_review") or [])

    if request.title is not None:
        job_parsed["title"] = request.title
        if "title" in needs_review:
            needs_review.remove("title")
    if request.company is not None:
        job_parsed["company"] = request.company
        if "company" in needs_review:
            needs_review.remove("company")

    job_parsed["needs_review"] = needs_review
    supabase.update_optimization_run(run_id, {"job_parsed": job_parsed})

    job_input = run.get("job_input") or ""
    job_url = job_input if job_input.startswith(("http://", "https://")) else None

    return OptimizationStatus(
        id=run["id"],
        status=run["status"],
        current_step=run.get("current_step"),
        iterations=run.get("iterations", 0),
        job_parsed=job_parsed,
        job_url=job_url,
        first_name=run.get("first_name"),
        last_name=run.get("last_name"),
        feedback=run.get("feedback"),
        result_html=run.get("result_html"),
        error=run.get("error"),
        timing=run.get("timing"),
        created_at=run["created_at"],
    )
```

Add `JobPatchRequest` to the import block at the top of the file:

```python
from hr_breaker.api.schemas import (
    JobPatchRequest,
    OptimizationListResponse,
    ...
)
```

**Step 5: Run tests to verify they pass**

```
pytest tests/test_optimize_routes.py -v
```

Expected: all 9 tests pass.

**Step 6: Commit**

```
git add src/hr_breaker/api/schemas.py src/hr_breaker/api/routes/optimize.py tests/test_optimize_routes.py
git commit -m "feat(api): PATCH /optimize/{id}/job to fix title/company manually"
```

---

## Frontend

### Task 4: Type + API client

**Files:**
- Modify: `frontend/src/types/index.ts:38-45`
- Modify: `frontend/src/lib/api.ts` (add new function)

**Step 1: Extend `JobParsed` type**

In `frontend/src/types/index.ts`, change `JobParsed` to:

```typescript
export interface JobParsed {
  title: string;
  company: string;
  location?: string;
  requirements: string[];
  responsibilities: string[];
  keywords: string[];
  needs_review?: string[];
}
```

`needs_review` is optional — old runs without it render as before.

**Step 2: Add API client function**

Add to `frontend/src/lib/api.ts` after `deleteOptimization` (line 176):

```typescript
export async function updateOptimizationJob(
  runId: string,
  patch: { title?: string; company?: string }
): Promise<OptimizationStatus> {
  return fetchWithAuth<OptimizationStatus>(`/optimize/${runId}/job`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
```

**Step 3: Verify typescript compiles**

```
cd frontend && npx tsc --noEmit
```

Expected: no errors.

**Step 4: Commit**

```
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add JobParsed.needs_review and updateOptimizationJob client"
```

---

### Task 5: `useUpdateOptimizationJob` hook

**Files:**
- Modify: `frontend/src/hooks/useOptimization.ts`

**Step 1: Add the mutation hook**

Append after `useDeleteOptimization`:

```typescript
export function useUpdateOptimizationJob(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: { title?: string; company?: string }) =>
      updateOptimizationJob(runId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["optimization", runId] });
      queryClient.invalidateQueries({ queryKey: ["optimizations"] });
    },
  });
}
```

Add `updateOptimizationJob` to the import at the top of the file:

```typescript
import {
  deleteOptimization,
  downloadOptimizationPDF,
  getOptimizationStatus,
  listOptimizations,
  startOptimization,
  updateOptimizationJob,
} from "@/lib/api";
```

> Note: `useOptimizationStatus` doesn't currently use TanStack Query (it owns its own `setState` + polling). Invalidating `["optimization", runId]` is forward-compatible if/when that hook is migrated; today the polling will pick up changes within ~2-5s anyway. We'll also expose the patched status directly to callers via the mutation `onSuccess` so the UI updates immediately — see Task 6.

**Step 2: Verify typescript compiles**

```
cd frontend && npx tsc --noEmit
```

**Step 3: Commit**

```
git add frontend/src/hooks/useOptimization.ts
git commit -m "feat(frontend): add useUpdateOptimizationJob hook"
```

---

### Task 6: Inline edit on results page

**Files:**
- Modify: `frontend/src/app/(protected)/results/[id]/page.tsx`

**Step 1: Replace the job info block**

Replace lines 156-187 (the `{/* Job info */}` `SlideUp`) with:

```tsx
{/* Job info */}
<SlideUp delay={0.1}>
  <JobInfoHeader
    runId={id}
    status={status}
    isComplete={isComplete}
    isFailed={isFailed}
  />
</SlideUp>
```

**Step 2: Add `JobInfoHeader` component above `ResultsPage`**

Insert before the `export default function ResultsPage(...)` line (around line 16):

```tsx
import { useState } from "react";
import EditPopup from "@/components/EditPopup";
import { useUpdateOptimizationJob } from "@/hooks/useOptimization";

type EditingField = "title" | "company" | null;

function JobInfoHeader({
  runId,
  status,
  isComplete,
  isFailed,
}: {
  runId: string;
  status: import("@/types").OptimizationStatus;
  isComplete: boolean;
  isFailed: boolean;
}) {
  const [editing, setEditing] = useState<EditingField>(null);
  const [popupPos, setPopupPos] = useState({ top: 0, left: 0 });
  const [localStatus, setLocalStatus] = useState(status);
  const update = useUpdateOptimizationJob(runId);

  const current = localStatus.job_parsed?.title === status.job_parsed?.title &&
    localStatus.job_parsed?.company === status.job_parsed?.company
    ? status
    : localStatus;

  const job = current.job_parsed;
  const needsReview = new Set(job?.needs_review ?? []);

  const openEditor = (field: "title" | "company", e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopupPos({ top: rect.bottom + 4, left: rect.left });
    setEditing(field);
  };

  const handleSave = async (newText: string) => {
    if (!editing) return;
    const trimmed = newText.trim();
    if (!trimmed) {
      setEditing(null);
      return;
    }
    const updated = await update.mutateAsync({ [editing]: trimmed });
    setLocalStatus(updated);
    setEditing(null);
  };

  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
        {!job ? (
          <span className="text-muted-foreground">Optimization in Progress</span>
        ) : needsReview.has("title") ? (
          <button
            onClick={(e) => openEditor("title", e)}
            className="inline-flex items-center gap-2 text-muted-foreground hover:text-foreground"
          >
            <span className="italic">Position not detected — click to set</span>
            <Pencil className="h-4 w-4" />
          </button>
        ) : (
          job.title
        )}
      </h1>
      {job && (
        <div className="flex flex-wrap items-center gap-4 text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Building2 className="h-4 w-4" />
            {needsReview.has("company") ? (
              <button
                onClick={(e) => openEditor("company", e)}
                className="inline-flex items-center gap-1.5 italic hover:text-foreground"
              >
                Company not detected — click to set
                <Pencil className="h-3.5 w-3.5" />
              </button>
            ) : (
              <span>{job.company}</span>
            )}
          </div>
          {job.location && (
            <div className="flex items-center gap-1.5">
              <MapPin className="h-4 w-4" />
              <span>{job.location}</span>
            </div>
          )}
        </div>
      )}
      {!isComplete && (
        <p className="text-muted-foreground">
          {isFailed
            ? "Optimization failed"
            : "Please wait while we optimize your resume"}
        </p>
      )}
      {editing && job && (
        <EditPopup
          text={
            editing === "title"
              ? needsReview.has("title")
                ? ""
                : job.title
              : needsReview.has("company")
              ? ""
              : job.company
          }
          position={popupPos}
          onSave={handleSave}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}
```

**Step 3: Manual verification (UI test)**

The frontend currently has no Jest/RTL setup, so do a manual smoke test:

```
# Terminal 1 — backend
uv run uvicorn hr_breaker.api.main:app --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open the app, run an optimization where the parser fails (use a recruiter/agency posting or paste plain text without an obvious company name). Verify:

1. Results page shows "Position not detected — click to set" / "Company not detected — click to set" with pencil icons in the appropriate spots.
2. Click → popup appears; typing + Save calls PATCH; UI immediately replaces the placeholder with entered text and pencil disappears.
3. Refresh the page → fixed values persist.
4. Open `/history` → corrected company/title visible in the row.
5. Run a normal optimization where parsing succeeds → no pencil shown anywhere.

Also verify: typescript compiles (`cd frontend && npx tsc --noEmit`) and lint passes (`cd frontend && npm run lint`) if configured.

**Step 4: Commit**

```
git add frontend/src/app/(protected)/results/\[id\]/page.tsx
git commit -m "feat(frontend): inline edit for title/company when parser failed"
```

---

## Final verification

**Step 1: Run full test suite**

```
pytest tests/ -v
```

Expected: All tests pass (existing + new tests from Task 1 and Task 3).

**Step 2: Smoke-test the full flow**

Repeat manual smoke test from Task 6, Step 3. Specifically check:

- Old optimization runs (created before this change, no `needs_review` key in their `job_parsed`) display as before — no pencils, no breakage.
- New runs that parse cleanly show no pencils.
- New runs that fail parsing show pencils on exactly the failed fields.
- Editing persists across page refresh and surfaces in `/history`.

**Step 3: Cleanup**

If we're on a feature branch, push and open a PR. If on `dev`, the per-task commits are already in.

---

## Out of scope (already excluded from design)

- Re-running optimization after the user fixes labels.
- Editing `location`, requirements, responsibilities, keywords.
- Pre-optimization confirmation step.
- Editing from the history list directly.
- Telegram bot flow (separate codebase, not affected).
