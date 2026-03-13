# Resume Editor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** After optimization, let users edit their resume via HTML code editor or LLM instructions, with a requirements checklist showing coverage.

**Architecture:** New `resume_editor` agent returns JSON patches. Three new API endpoints (requirements, edit, validate). Frontend adds editor page with Monaco, iframe preview, requirements panel, and instruction bar. Server applies patches via BeautifulSoup as fallback.

**Tech Stack:** Pydantic-AI (flash model), BeautifulSoup4, FastAPI, Monaco Editor (@monaco-editor/react), React Query, Tailwind CSS.

---

### Task 1: Backend — Pydantic models for editor

**Files:**
- Create: `src/hr_breaker/models/editor.py`
- Modify: `src/hr_breaker/models/__init__.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

```python
# tests/test_models.py — append to existing file

from hr_breaker.models.editor import ResumePatch, EditResult, RequirementItem

def test_resume_patch_model():
    patch = ResumePatch(selector="#skills-list", action="append", html="<li>Python</li>")
    assert patch.selector == "#skills-list"
    assert patch.action == "append"
    assert patch.html == "<li>Python</li>"

def test_resume_patch_remove_no_html():
    patch = ResumePatch(selector="#experience-item-0", action="remove", html=None)
    assert patch.action == "remove"
    assert patch.html is None

def test_edit_result_model():
    result = EditResult(
        patches=[ResumePatch(selector="#summary", action="replace", html="<p>New summary</p>")],
        reasoning="Updated summary to emphasize leadership"
    )
    assert len(result.patches) == 1
    assert result.reasoning

def test_requirement_item_model():
    req = RequirementItem(id="req_1", text="3+ years Python", covered=True)
    assert req.covered is True
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_resume_patch_model -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hr_breaker.models.editor'`

**Step 3: Write minimal implementation**

```python
# src/hr_breaker/models/editor.py
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class ResumePatch(BaseModel):
    selector: str
    action: Literal["replace", "append", "prepend", "remove"]
    html: str | None = None


class EditResult(BaseModel):
    patches: list[ResumePatch]
    reasoning: str


class RequirementItem(BaseModel):
    id: str
    text: str
    covered: bool
```

Then add to `src/hr_breaker/models/__init__.py`:
```python
from hr_breaker.models.editor import EditResult, RequirementItem, ResumePatch
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -k "resume_patch or edit_result or requirement_item" -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/hr_breaker/models/editor.py src/hr_breaker/models/__init__.py tests/test_models.py
git commit -m "feat: add editor models (ResumePatch, EditResult, RequirementItem)"
```

---

### Task 2: Backend — Requirements matching service

**Files:**
- Create: `src/hr_breaker/services/requirements_matcher.py`
- Test: `tests/test_requirements_matcher.py`

**Step 1: Write the failing test**

```python
# tests/test_requirements_matcher.py
from hr_breaker.models import JobPosting, RequirementItem
from hr_breaker.services.requirements_matcher import match_requirements


def _make_job(**kwargs) -> JobPosting:
    defaults = dict(
        title="Software Engineer",
        company="Acme",
        location="Remote",
        requirements=["3+ years Python", "Experience with Kubernetes", "CI/CD pipelines"],
        responsibilities=["Build features"],
        keywords=["Python", "Kubernetes", "CI/CD", "Docker"],
        description="Software engineer role",
        raw_text="Full posting text",
    )
    defaults.update(kwargs)
    return JobPosting(**defaults)


def test_match_requirements_all_covered():
    job = _make_job()
    html = "<p>Python developer with 5 years experience. Kubernetes clusters. CI/CD pipelines with Docker.</p>"
    results = match_requirements(job, html)
    assert all(r.covered for r in results)


def test_match_requirements_partial():
    job = _make_job()
    html = "<p>Python developer with 5 years experience.</p>"
    results = match_requirements(job, html)
    covered = [r for r in results if r.covered]
    uncovered = [r for r in results if not r.covered]
    assert len(covered) >= 1
    assert len(uncovered) >= 1


def test_match_requirements_case_insensitive():
    job = _make_job(requirements=["Python experience"], keywords=["python"])
    html = "<p>PYTHON developer</p>"
    results = match_requirements(job, html)
    python_reqs = [r for r in results if "python" in r.text.lower() or "Python" in r.text]
    assert any(r.covered for r in python_reqs)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_requirements_matcher.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/hr_breaker/services/requirements_matcher.py
"""Match job requirements against resume HTML content."""
from __future__ import annotations

import re

from hr_breaker.models import JobPosting, RequirementItem


def match_requirements(job: JobPosting, html: str) -> list[RequirementItem]:
    """Check which job requirements are covered in resume HTML."""
    text = _strip_html(html).lower()
    items: list[RequirementItem] = []

    for i, req in enumerate(job.requirements):
        # Extract significant words (3+ chars) from requirement
        words = [w for w in re.findall(r"[a-zA-Z\-/+#.]+", req) if len(w) >= 3]
        # Requirement is covered if majority of significant words appear
        if not words:
            items.append(RequirementItem(id=f"req_{i}", text=req, covered=True))
            continue
        matched = sum(1 for w in words if w.lower() in text)
        covered = matched / len(words) >= 0.5
        items.append(RequirementItem(id=f"req_{i}", text=req, covered=covered))

    # Also check keywords not already in requirements
    req_text_lower = " ".join(job.requirements).lower()
    for j, kw in enumerate(job.keywords):
        if kw.lower() in req_text_lower:
            continue
        covered = kw.lower() in text
        items.append(RequirementItem(id=f"kw_{j}", text=kw, covered=covered))

    return items


def _strip_html(html: str) -> str:
    """Remove HTML tags, return plain text."""
    return re.sub(r"<[^>]+>", " ", html)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_requirements_matcher.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/hr_breaker/services/requirements_matcher.py tests/test_requirements_matcher.py
git commit -m "feat: add requirements matcher service"
```

---

### Task 3: Backend — Server-side patch application

**Files:**
- Create: `src/hr_breaker/services/patch_applier.py`
- Test: `tests/test_patch_applier.py`

**Step 1: Write the failing test**

```python
# tests/test_patch_applier.py
from hr_breaker.models.editor import ResumePatch
from hr_breaker.services.patch_applier import apply_patches


SAMPLE_HTML = """
<div id="summary"><p>Software engineer</p></div>
<div id="skills-list"><ul><li>Java</li></ul></div>
<div id="experience-item-0"><ul><li>Built APIs</li></ul></div>
"""


def test_append_patch():
    patch = ResumePatch(selector="#skills-list ul", action="append", html="<li>Python</li>")
    result = apply_patches(SAMPLE_HTML, [patch])
    assert "<li>Python</li>" in result
    assert "<li>Java</li>" in result


def test_replace_patch():
    patch = ResumePatch(selector="#summary p", action="replace", html="<p>Senior engineer</p>")
    result = apply_patches(SAMPLE_HTML, [patch])
    assert "Senior engineer" in result
    assert "Software engineer" not in result


def test_remove_patch():
    patch = ResumePatch(selector="#experience-item-0", action="remove", html=None)
    result = apply_patches(SAMPLE_HTML, [patch])
    assert "experience-item-0" not in result
    assert "Built APIs" not in result


def test_prepend_patch():
    patch = ResumePatch(selector="#skills-list ul", action="prepend", html="<li>Leadership</li>")
    result = apply_patches(SAMPLE_HTML, [patch])
    assert result.index("Leadership") < result.index("Java")


def test_missing_selector_skipped():
    patch = ResumePatch(selector="#nonexistent", action="replace", html="<p>x</p>")
    result = apply_patches(SAMPLE_HTML, [patch])
    assert result.strip() == SAMPLE_HTML.strip()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_patch_applier.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Check BeautifulSoup is available, then implement**

Run: `uv run python -c "import bs4; print(bs4.__version__)"` — if missing, `uv add beautifulsoup4`

```python
# src/hr_breaker/services/patch_applier.py
"""Apply CSS-selector-based patches to HTML."""
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from hr_breaker.config import logger
from hr_breaker.models.editor import ResumePatch


def apply_patches(html: str, patches: list[ResumePatch]) -> str:
    """Apply patches to HTML string. Skips patches with missing selectors."""
    soup = BeautifulSoup(html, "html.parser")

    for patch in patches:
        target = soup.select_one(patch.selector)
        if target is None:
            logger.warning(f"Patch selector not found: {patch.selector}")
            continue

        if patch.action == "remove":
            target.decompose()
        elif patch.action == "replace":
            new = BeautifulSoup(patch.html or "", "html.parser")
            target.replace_with(new)
        elif patch.action == "append":
            fragment = BeautifulSoup(patch.html or "", "html.parser")
            for child in list(fragment.children):
                target.append(child)
        elif patch.action == "prepend":
            fragment = BeautifulSoup(patch.html or "", "html.parser")
            children = list(fragment.children)
            for child in reversed(children):
                target.insert(0, child)

    return str(soup)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_patch_applier.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add src/hr_breaker/services/patch_applier.py tests/test_patch_applier.py
git commit -m "feat: add HTML patch applier service"
```

---

### Task 4: Backend — resume_editor agent

**Files:**
- Create: `src/hr_breaker/agents/resume_editor.py`
- Modify: `src/hr_breaker/agents/__init__.py`
- Test: `tests/test_resume_editor.py`

**Step 1: Write the failing test**

```python
# tests/test_resume_editor.py
import pytest
from hr_breaker.agents.resume_editor import edit_resume
from hr_breaker.models.editor import EditResult


@pytest.mark.asyncio
async def test_edit_resume_returns_edit_result():
    """Integration test — calls real LLM. Use flash model for cost."""
    html = '<div id="summary"><p>Software engineer with Java experience</p></div>'
    original = "Software engineer with 5 years Java and 3 years Python experience"
    instruction = "Add Python to the summary"

    result = await edit_resume(html, original, instruction)
    assert isinstance(result, EditResult)
    assert len(result.patches) >= 1
    assert result.reasoning
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resume_editor.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/hr_breaker/agents/resume_editor.py
"""Agent for editing resumes via LLM-generated patches."""
from __future__ import annotations

from pydantic_ai import Agent

from hr_breaker.config import get_settings
from hr_breaker.models.editor import EditResult

_SYSTEM_PROMPT = """\
You are a resume editor. You receive:
1. Current HTML resume
2. The user's original resume text (source of truth — never fabricate)
3. An editing instruction

Return JSON patches to apply to the HTML. Each patch has:
- selector: CSS selector targeting the element (use IDs like #summary, #skills-list, #experience-item-0)
- action: "replace" | "append" | "prepend" | "remove"
- html: new HTML content (null for remove)

Rules:
- ONLY use information from the original resume. Never invent skills, companies, metrics.
- Make MINIMAL changes — only what the instruction asks for.
- Keep the same HTML structure and CSS classes.
- Provide brief reasoning for your changes.
"""


def _make_agent() -> Agent[None, EditResult]:
    settings = get_settings()
    return Agent(
        f"google-gla:{settings.gemini_flash_model}",
        system_prompt=_SYSTEM_PROMPT,
        output_type=EditResult,
        model_settings={"temperature": 0.2},
    )


async def edit_resume(html: str, original_resume: str, instruction: str) -> EditResult:
    """Edit resume HTML based on instruction, returning patches."""
    agent = _make_agent()
    prompt = f"""## Current HTML Resume
```html
{html}
```

## Original Resume (source of truth)
```
{original_resume}
```

## Instruction
{instruction}
"""
    result = await agent.run(prompt)
    return result.output
```

Add to `src/hr_breaker/agents/__init__.py`:
```python
from hr_breaker.agents.resume_editor import edit_resume
```

**Step 4: Run test to verify it passes**

Run: `GEMINI_FLASH_MODEL=gemini-2.5-flash uv run pytest tests/test_resume_editor.py -v`
Expected: 1 PASSED (uses real LLM — keep flash model for cost)

**Step 5: Commit**

```bash
git add src/hr_breaker/agents/resume_editor.py src/hr_breaker/agents/__init__.py tests/test_resume_editor.py
git commit -m "feat: add resume_editor agent with patch output"
```

---

### Task 5: Backend — API endpoints

**Files:**
- Create: `src/hr_breaker/api/routes/editor.py`
- Modify: `src/hr_breaker/api/app.py` (or wherever router is mounted)
- Test: `tests/test_editor_api.py`

**Step 1: Write the failing test**

```python
# tests/test_editor_api.py
import pytest
from unittest.mock import AsyncMock, patch

from hr_breaker.models import JobPosting
from hr_breaker.models.editor import RequirementItem, ResumePatch, EditResult


def _make_job() -> dict:
    return JobPosting(
        title="Software Engineer",
        company="Acme",
        location="Remote",
        requirements=["3+ years Python", "Kubernetes experience"],
        responsibilities=["Build features"],
        keywords=["Python", "Kubernetes", "Docker"],
        description="SE role",
        raw_text="Full text",
    ).model_dump()


class TestRequirementsEndpoint:
    """Tests for GET /api/optimize/{id}/requirements"""

    @pytest.mark.asyncio
    async def test_returns_requirements_list(self, client, mock_supabase):
        mock_supabase.get_optimization_run.return_value = {
            "id": "run-1",
            "user_id": "user-1",
            "status": "complete",
            "result_html": "<p>Python developer with Kubernetes</p>",
            "job_parsed": _make_job(),
        }
        resp = await client.get("/api/optimize/run-1/requirements")
        assert resp.status_code == 200
        data = resp.json()
        assert "requirements" in data
        assert isinstance(data["requirements"], list)


class TestValidateEndpoint:
    """Tests for POST /api/optimize/{id}/validate"""

    @pytest.mark.asyncio
    async def test_validates_html(self, client, mock_supabase):
        mock_supabase.get_optimization_run.return_value = {
            "id": "run-1",
            "user_id": "user-1",
            "status": "complete",
            "result_html": "<p>Some resume</p>",
            "job_parsed": _make_job(),
        }
        resp = await client.post(
            "/api/optimize/run-1/validate",
            json={"html": "<p>Updated resume with Python and Kubernetes</p>"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "requirements" in data
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_editor_api.py -v`
Expected: FAIL — import errors

**Step 3: Write implementation**

```python
# src/hr_breaker/api/routes/editor.py
"""Resume editor API endpoints."""
from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from hr_breaker.api.auth import get_current_user
from hr_breaker.models import JobPosting
from hr_breaker.models.editor import RequirementItem, ResumePatch
from hr_breaker.services.requirements_matcher import match_requirements
from hr_breaker.services.patch_applier import apply_patches
from hr_breaker.services.supabase import get_supabase_service
from hr_breaker.agents.resume_editor import edit_resume

router = APIRouter()


class EditRequest(BaseModel):
    instruction: str
    html: str  # current HTML state from frontend


class EditResponse(BaseModel):
    patches: list[dict]
    updated_html: str


class ValidateRequest(BaseModel):
    html: str


class ValidateResponse(BaseModel):
    results: list[dict]
    requirements: list[RequirementItem]


class RequirementsResponse(BaseModel):
    requirements: list[RequirementItem]


async def _get_run(run_id: str, user_id: str) -> dict:
    supa = get_supabase_service()
    run = await supa.get_optimization_run(run_id)
    if not run or run.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Optimization not complete")
    return run


@router.get("/optimize/{run_id}/requirements", response_model=RequirementsResponse)
async def get_requirements(run_id: str, user=get_current_user):
    run = await _get_run(run_id, user.id)
    job = JobPosting.model_validate(run["job_parsed"])
    html = run.get("result_html", "")
    items = match_requirements(job, html)
    return RequirementsResponse(requirements=items)


@router.post("/optimize/{run_id}/edit", response_model=EditResponse)
async def edit_resume_endpoint(run_id: str, req: EditRequest, user=get_current_user):
    run = await _get_run(run_id, user.id)

    # Get original resume text for hallucination prevention
    supa = get_supabase_service()
    cv = await supa.get_cv(run.get("cv_id", ""))
    original = cv.get("content_text", "") if cv else ""

    result = await edit_resume(req.html, original, req.instruction)
    updated_html = apply_patches(req.html, result.patches)

    return EditResponse(
        patches=[p.model_dump() for p in result.patches],
        updated_html=updated_html,
    )


@router.post("/optimize/{run_id}/validate", response_model=ValidateResponse)
async def validate_resume(run_id: str, req: ValidateRequest, user=get_current_user):
    run = await _get_run(run_id, user.id)
    job = JobPosting.model_validate(run["job_parsed"])

    # Run lightweight filters only
    from hr_breaker.filters import KeywordMatcher, ContentLengthChecker
    from hr_breaker.models import OptimizedResume, ResumeSource

    source = ResumeSource(content="", checksum="")  # minimal, only needed for filter interface
    optimized = OptimizedResume(html=req.html, iteration=0, changes=[], source_checksum="")

    results = []
    for filter_cls in [ContentLengthChecker, KeywordMatcher]:
        f = filter_cls()
        result = await f.evaluate(optimized, job, source)
        results.append(result.model_dump())

    requirements = match_requirements(job, req.html)
    return ValidateResponse(results=results, requirements=requirements)
```

Mount router in app — find where other routers are included and add:
```python
from hr_breaker.api.routes.editor import router as editor_router
app.include_router(editor_router, prefix="/api")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_editor_api.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/editor.py tests/test_editor_api.py
git commit -m "feat: add editor API endpoints (requirements, edit, validate)"
```

---

### Task 6: Backend — Update optimizer prompt to require HTML IDs

**Files:**
- Modify: `src/hr_breaker/agents/optimizer.py`
- Modify: `templates/resume_guide.md`

**Step 1: Read current optimizer prompt and resume guide**

Read `src/hr_breaker/agents/optimizer.py` — find system prompt section.
Read `templates/resume_guide.md` — find HTML structure section.

**Step 2: Add ID requirements to resume guide**

Add to the HTML structure section of `templates/resume_guide.md`:
```markdown
## Required ID Attributes

Every section MUST have a predictable id attribute for post-generation editing:
- `<div id="summary">` — Summary/objective section
- `<div id="experience">` — Experience section container
- `<div id="experience-item-0">`, `<div id="experience-item-1">`, etc. — Individual experience entries
- `<div id="education">` — Education section
- `<div id="skills-list">` — Skills section
- `<div id="projects">` — Projects section (if present)
- `<div id="certifications">` — Certifications section (if present)
```

**Step 3: Verify optimizer uses resume_guide.md**

Check that optimizer agent loads and uses the guide. If not, ensure the guide content is included in the system prompt.

**Step 4: Test manually**

Run one optimization with debug mode to verify generated HTML contains id attributes:
```bash
GEMINI_FLASH_MODEL=gemini-2.5-flash uv run hr-breaker optimize test_resume.txt test_job.txt -d
```
Check `output/debug_*/` for HTML with IDs.

**Step 5: Commit**

```bash
git add templates/resume_guide.md src/hr_breaker/agents/optimizer.py
git commit -m "feat: require HTML ID attributes for editor patch targeting"
```

---

### Task 7: Frontend — Install Monaco and add TypeScript types

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Step 1: Install Monaco editor**

```bash
cd frontend && npm install @monaco-editor/react
```

**Step 2: Add TypeScript types**

Append to `frontend/src/types/index.ts`:
```typescript
export interface ResumePatch {
  selector: string;
  action: "replace" | "append" | "prepend" | "remove";
  html: string | null;
}

export interface EditResponse {
  patches: ResumePatch[];
  updated_html: string;
}

export interface RequirementItem {
  id: string;
  text: string;
  covered: boolean;
}

export interface RequirementsResponse {
  requirements: RequirementItem[];
}

export interface FilterResultLight {
  filter_name: string;
  passed: boolean;
  score: number;
  threshold: number;
  issues: string[];
  suggestions: string[];
}

export interface ValidateResponse {
  results: FilterResultLight[];
  requirements: RequirementItem[];
}
```

**Step 3: Add API functions**

Append to `frontend/src/lib/api.ts`:
```typescript
import type { RequirementsResponse, EditResponse, ValidateResponse } from "@/types";

export async function getRequirements(runId: string): Promise<RequirementsResponse> {
  return fetchWithAuth<RequirementsResponse>(`/optimize/${runId}/requirements`);
}

export async function editResume(runId: string, instruction: string, html: string): Promise<EditResponse> {
  return fetchWithAuth<EditResponse>(`/optimize/${runId}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction, html }),
  });
}

export async function validateResume(runId: string, html: string): Promise<ValidateResponse> {
  return fetchWithAuth<ValidateResponse>(`/optimize/${runId}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
}

export async function downloadPdfFromHtml(runId: string, html: string): Promise<Blob> {
  return fetchWithAuth<Blob>(`/optimize/${runId}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
}
```

**Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no type errors.

**Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add editor types and API functions to frontend"
```

---

### Task 8: Frontend — useResumeEditor hook

**Files:**
- Create: `frontend/src/hooks/useResumeEditor.ts`

**Step 1: Write the hook**

```typescript
// frontend/src/hooks/useResumeEditor.ts
"use client";
import { useState, useCallback, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getRequirements, editResume, validateResume } from "@/lib/api";
import type { RequirementItem, ValidateResponse, EditResponse, FilterResultLight } from "@/types";

export function useResumeEditor(runId: string, initialHtml: string) {
  const [html, setHtml] = useState(initialHtml);
  const [history, setHistory] = useState<string[]>([initialHtml]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Requirements
  const requirementsQuery = useQuery({
    queryKey: ["requirements", runId, html],
    queryFn: () => validateResume(runId, html).then((r) => r.requirements),
    enabled: !!html,
    staleTime: 5000,
  });

  // Validation
  const [validationResults, setValidationResults] = useState<FilterResultLight[]>([]);

  const runValidation = useCallback(
    async (currentHtml: string) => {
      const res = await validateResume(runId, currentHtml);
      setValidationResults(res.results);
      return res;
    },
    [runId]
  );

  // Push to history
  const pushHtml = useCallback(
    (newHtml: string) => {
      setHtml(newHtml);
      setHistory((prev) => [...prev.slice(0, historyIndex + 1), newHtml]);
      setHistoryIndex((i) => i + 1);

      // Debounced validation
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => runValidation(newHtml), 1000);
    },
    [historyIndex, runValidation]
  );

  // Manual HTML edit (from Monaco)
  const updateHtml = useCallback(
    (newHtml: string) => {
      pushHtml(newHtml);
    },
    [pushHtml]
  );

  // LLM edit
  const editMutation = useMutation({
    mutationFn: (instruction: string) => editResume(runId, instruction, html),
    onSuccess: (data: EditResponse) => {
      pushHtml(data.updated_html);
    },
  });

  // Undo
  const undo = useCallback(() => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setHistoryIndex(newIndex);
      setHtml(history[newIndex]);
    }
  }, [history, historyIndex]);

  // Redo
  const redo = useCallback(() => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setHistoryIndex(newIndex);
      setHtml(history[newIndex]);
    }
  }, [history, historyIndex]);

  return {
    html,
    updateHtml,
    requirements: requirementsQuery.data ?? [],
    requirementsLoading: requirementsQuery.isLoading,
    validationResults,
    sendInstruction: editMutation.mutate,
    isEditing: editMutation.isPending,
    editError: editMutation.error,
    undo,
    redo,
    canUndo: historyIndex > 0,
    canRedo: historyIndex < history.length - 1,
  };
}
```

**Step 2: Verify build**

```bash
cd frontend && npm run build
```
Expected: Passes

**Step 3: Commit**

```bash
git add frontend/src/hooks/useResumeEditor.ts
git commit -m "feat: add useResumeEditor hook with undo/redo and validation"
```

---

### Task 9: Frontend — RequirementsChecklist component

**Files:**
- Create: `frontend/src/components/RequirementsChecklist.tsx`

**Step 1: Write the component**

```tsx
// frontend/src/components/RequirementsChecklist.tsx
"use client";
import { useState } from "react";
import { Check, X, Send } from "lucide-react";
import type { RequirementItem } from "@/types";

interface Props {
  requirements: RequirementItem[];
  loading: boolean;
  onAddRequirement: (instruction: string) => void;
  isEditing: boolean;
}

export default function RequirementsChecklist({ requirements, loading, onAddRequirement, isEditing }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [customInstruction, setCustomInstruction] = useState("");

  const covered = requirements.filter((r) => r.covered);
  const uncovered = requirements.filter((r) => !r.covered);

  const handleClick = (req: RequirementItem) => {
    if (req.covered) return;
    const defaultInstruction = `Add to resume: ${req.text}`;
    setEditingId(req.id);
    setCustomInstruction(defaultInstruction);
  };

  const handleSend = () => {
    if (!customInstruction.trim()) return;
    onAddRequirement(customInstruction);
    setEditingId(null);
    setCustomInstruction("");
  };

  if (loading) {
    return <div className="animate-pulse space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-8 bg-muted rounded" />)}</div>;
  }

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-muted-foreground">
        {covered.length}/{requirements.length} covered
      </div>

      {uncovered.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase text-destructive">Missing</div>
          {uncovered.map((req) => (
            <div key={req.id}>
              <button
                onClick={() => handleClick(req)}
                disabled={isEditing}
                className="flex items-center gap-2 w-full text-left text-sm p-2 rounded hover:bg-destructive/10 transition-colors disabled:opacity-50"
              >
                <X className="h-4 w-4 text-destructive shrink-0" />
                <span>{req.text}</span>
              </button>
              {editingId === req.id && (
                <div className="flex gap-2 ml-6 mt-1">
                  <input
                    value={customInstruction}
                    onChange={(e) => setCustomInstruction(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSend()}
                    className="flex-1 text-sm border rounded px-2 py-1"
                    autoFocus
                  />
                  <button onClick={handleSend} disabled={isEditing} className="p-1 hover:bg-muted rounded">
                    <Send className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {covered.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase text-green-600">Covered</div>
          {covered.map((req) => (
            <div key={req.id} className="flex items-center gap-2 text-sm p-2 text-muted-foreground">
              <Check className="h-4 w-4 text-green-600 shrink-0" />
              <span>{req.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Verify build**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

```bash
git add frontend/src/components/RequirementsChecklist.tsx
git commit -m "feat: add RequirementsChecklist component"
```

---

### Task 10: Frontend — Editor page

**Files:**
- Create: `frontend/src/app/(protected)/results/[id]/edit/page.tsx`

**Step 1: Write the editor page**

```tsx
// frontend/src/app/(protected)/results/[id]/edit/page.tsx
"use client";
import { use, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Undo2, Redo2, Download, Eye, Code } from "lucide-react";
import { useResumeEditor } from "@/hooks/useResumeEditor";
import { useOptimizationStatus } from "@/hooks/useOptimization";
import RequirementsChecklist from "@/components/RequirementsChecklist";
import { downloadPdfFromHtml } from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

export default function EditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { status } = useOptimizationStatus(id);
  const [mode, setMode] = useState<"preview" | "code">("preview");
  const [downloading, setDownloading] = useState(false);
  const [instruction, setInstruction] = useState("");

  const {
    html, updateHtml, requirements, requirementsLoading,
    validationResults, sendInstruction, isEditing,
    undo, redo, canUndo, canRedo,
  } = useResumeEditor(id, status?.result_html ?? "");

  const handleSendInstruction = () => {
    if (!instruction.trim()) return;
    sendInstruction(instruction);
    setInstruction("");
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const blob = await downloadPdfFromHtml(id, html);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "resume.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  if (!status?.result_html) {
    return <div className="p-8 text-center text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Left panel — Requirements */}
      <div className="w-72 border-r overflow-y-auto p-4">
        <h2 className="font-semibold mb-3">Requirements</h2>
        <RequirementsChecklist
          requirements={requirements}
          loading={requirementsLoading}
          onAddRequirement={sendInstruction}
          isEditing={isEditing}
        />

        {/* Validation scores */}
        {validationResults.length > 0 && (
          <div className="mt-6 space-y-2">
            <h3 className="text-sm font-semibold">Scores</h3>
            {validationResults.map((r) => (
              <div key={r.filter_name} className="flex justify-between text-sm">
                <span>{r.filter_name}</span>
                <span className={r.passed ? "text-green-600" : "text-amber-600"}>
                  {(r.score * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Center — Preview/Editor */}
      <div className="flex-1 flex flex-col">
        {/* Toolbar */}
        <div className="flex items-center gap-2 border-b p-2">
          <button onClick={undo} disabled={!canUndo} className="p-2 hover:bg-muted rounded disabled:opacity-30">
            <Undo2 className="h-4 w-4" />
          </button>
          <button onClick={redo} disabled={!canRedo} className="p-2 hover:bg-muted rounded disabled:opacity-30">
            <Redo2 className="h-4 w-4" />
          </button>
          <div className="flex-1" />
          <button
            onClick={() => setMode(mode === "preview" ? "code" : "preview")}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border rounded hover:bg-muted"
          >
            {mode === "preview" ? <Code className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            {mode === "preview" ? "Code" : "Preview"}
          </button>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            <Download className="h-4 w-4" />
            {downloading ? "..." : "PDF"}
          </button>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-auto">
          {mode === "preview" ? (
            <div className="max-w-[8.5in] mx-auto bg-white shadow-md my-4">
              <iframe
                srcDoc={`<!DOCTYPE html><html><head><style>body{font-family:'Times New Roman',serif;font-size:11pt;margin:0.4in;line-height:1.25;}</style></head><body>${html}</body></html>`}
                className="w-full h-[11in] border-0"
                title="Resume preview"
              />
            </div>
          ) : (
            <MonacoEditor
              height="100%"
              language="html"
              value={html}
              onChange={(value) => value !== undefined && updateHtml(value)}
              options={{ minimap: { enabled: false }, wordWrap: "on", fontSize: 13 }}
            />
          )}
        </div>

        {/* Bottom — Instruction bar */}
        <div className="border-t p-3 flex gap-2">
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSendInstruction()}
            placeholder="Tell AI what to change... (e.g. 'add more about leadership')"
            className="flex-1 border rounded px-3 py-2 text-sm"
            disabled={isEditing}
          />
          <button
            onClick={handleSendInstruction}
            disabled={isEditing || !instruction.trim()}
            className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          >
            {isEditing ? "Applying..." : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify build**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

```bash
git add frontend/src/app/\(protected\)/results/\[id\]/edit/page.tsx
git commit -m "feat: add resume editor page with preview, Monaco, and instruction bar"
```

---

### Task 11: Frontend — Add "Edit" button to results page

**Files:**
- Modify: `frontend/src/app/(protected)/results/[id]/page.tsx`

**Step 1: Read the current results page**

Read the file to find where the download button is rendered.

**Step 2: Add Edit button next to Download**

Add a link/button that navigates to `/results/{id}/edit`:
```tsx
import Link from "next/link";
import { Pencil } from "lucide-react";

// ... inside the completed state section, near the download button:
<Link
  href={`/results/${id}/edit`}
  className="flex items-center gap-2 px-4 py-2 border rounded hover:bg-muted"
>
  <Pencil className="h-4 w-4" />
  Edit Resume
</Link>
```

**Step 3: Verify build**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add frontend/src/app/\(protected\)/results/\[id\]/page.tsx
git commit -m "feat: add Edit Resume button to results page"
```

---

### Task 12: Backend — Add download endpoint for edited HTML

**Files:**
- Modify: `src/hr_breaker/api/routes/editor.py`

**Step 1: Add PDF download endpoint**

Append to `editor.py`:
```python
class DownloadRequest(BaseModel):
    html: str


@router.post("/optimize/{run_id}/download")
async def download_edited_pdf(run_id: str, req: DownloadRequest, user=get_current_user):
    await _get_run(run_id, user.id)
    from hr_breaker.services.renderer import HTMLRenderer
    from fastapi.responses import Response

    renderer = HTMLRenderer()
    result = renderer.render(req.html)
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=resume_{run_id}.pdf"},
    )
```

**Step 2: Test manually**

```bash
curl -X POST http://localhost:8000/api/optimize/test-id/download \
  -H "Content-Type: application/json" \
  -d '{"html": "<p>Test</p>"}' \
  -o test.pdf
```

**Step 3: Commit**

```bash
git add src/hr_breaker/api/routes/editor.py
git commit -m "feat: add PDF download endpoint for edited resumes"
```

---

### Task 13: Integration test — Full edit flow

**Files:**
- Create: `tests/test_editor_integration.py`

**Step 1: Write integration test**

```python
# tests/test_editor_integration.py
"""End-to-end test for the resume editor flow."""
import pytest
from hr_breaker.models import JobPosting
from hr_breaker.models.editor import EditResult, ResumePatch
from hr_breaker.services.requirements_matcher import match_requirements
from hr_breaker.services.patch_applier import apply_patches


def test_full_edit_flow():
    """Simulate: check requirements → apply patch → re-check."""
    job = JobPosting(
        title="Python Developer",
        company="Acme",
        location="Remote",
        requirements=["5+ years Python", "Docker experience", "REST API design"],
        responsibilities=["Build services"],
        keywords=["Python", "Docker", "REST", "FastAPI"],
        description="Python dev role",
        raw_text="Full text",
    )

    html = '<div id="summary"><p>Java developer with 10 years experience</p></div>'

    # Step 1: Check requirements — most should be uncovered
    reqs = match_requirements(job, html)
    uncovered_before = [r for r in reqs if not r.covered]
    assert len(uncovered_before) >= 2

    # Step 2: Apply patches manually (simulating LLM output)
    patches = [
        ResumePatch(selector="#summary p", action="replace",
                    html="<p>Python developer with 5 years experience. Built REST APIs with FastAPI and Docker.</p>"),
    ]
    updated = apply_patches(html, patches)
    assert "Python" in updated
    assert "Docker" in updated

    # Step 3: Re-check — more should be covered now
    reqs_after = match_requirements(job, updated)
    uncovered_after = [r for r in reqs_after if not r.covered]
    assert len(uncovered_after) < len(uncovered_before)
```

**Step 2: Run test**

Run: `uv run pytest tests/test_editor_integration.py -v`
Expected: 1 PASSED

**Step 3: Commit**

```bash
git add tests/test_editor_integration.py
git commit -m "test: add editor integration test for full edit flow"
```
