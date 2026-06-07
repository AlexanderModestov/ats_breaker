# Optimizer V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a second resume optimizer (v2) that applies an 8-dimension coaching approach from the interview-coach-skill, producing the same HTML/PDF artifact plus a structured audit score, selectable via `OPTIMIZER_VERSION` env flag.

**Architecture:** v2 slots into the same pipeline as v1 (same input, same renderer, same 5 filters). A new `optimizer_v2.py` agent replaces the system prompt; a new `AuditScore` model is added as an optional field on `OptimizedResume`; `orchestration.py` routes to v1 or v2 based on the flag. No changes to filters, renderer, or job parser.

**Tech Stack:** Python, Pydantic AI, Pydantic v2, Google Gemini Pro, FastAPI

---

## Task 1: AuditScore model

**Files:**
- Create: `src/hr_breaker/models/audit.py`
- Modify: `src/hr_breaker/models/__init__.py`
- Test: `tests/test_models.py`

### Step 1: Write the failing test

Add to `tests/test_models.py`:

```python
from hr_breaker.models.audit import AuditScore

def test_audit_score_valid():
    score = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Moderate",
        seniority_calibration="Aligned",
        keyword_coverage="Weak",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Needs Work",
        top_fixes=["Add quantification to bullets", "Reorder skills by relevance", "Tighten summary hook"],
    )
    assert score.ats_compatibility == "ATS-Ready"
    assert score.overall == "Needs Work"
    assert len(score.top_fixes) == 3


def test_audit_score_rejects_invalid_literal():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AuditScore(
            ats_compatibility="Unknown",  # invalid
            recruiter_scan="Strong",
            bullet_quality="Strong",
            seniority_calibration="Aligned",
            keyword_coverage="Strong",
            structure="Strong",
            concern_management="NA",
            consistency="Strong",
            overall="Strong",
            top_fixes=[],
        )
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_models.py::test_audit_score_valid tests/test_models.py::test_audit_score_rejects_invalid_literal -v
```

Expected: FAIL with `ImportError: cannot import name 'AuditScore'`

### Step 3: Create `src/hr_breaker/models/audit.py`

```python
from typing import Literal
from pydantic import BaseModel


class AuditScore(BaseModel):
    ats_compatibility: Literal["ATS-Ready", "ATS-Risky", "ATS-Broken"]
    recruiter_scan: Literal["Strong", "Moderate", "Weak"]
    bullet_quality: Literal["Strong", "Moderate", "Weak"]
    seniority_calibration: Literal["Aligned", "Mismatched"]
    keyword_coverage: Literal["Strong", "Moderate", "Weak"]
    structure: Literal["Strong", "Moderate", "Weak"]
    concern_management: Literal["Strong", "Moderate", "Weak", "NA"]
    consistency: Literal["Strong", "Moderate", "Weak"]
    overall: Literal["Strong", "Needs Work", "Weak"]
    top_fixes: list[str]  # 3 priority-ordered fixes
```

### Step 4: Export from `src/hr_breaker/models/__init__.py`

Add import line after `from .resume import ResumeSource, OptimizedResume`:

```python
from .audit import AuditScore
```

Add `"AuditScore"` to the `__all__` list.

### Step 5: Run tests to verify they pass

```bash
uv run pytest tests/test_models.py::test_audit_score_valid tests/test_models.py::test_audit_score_rejects_invalid_literal -v
```

Expected: PASS

### Step 6: Commit

```bash
git add src/hr_breaker/models/audit.py src/hr_breaker/models/__init__.py tests/test_models.py
git commit -m "feat: add AuditScore model for optimizer v2"
```

---

## Task 2: Add `audit` field to `OptimizedResume`

**Files:**
- Modify: `src/hr_breaker/models/resume.py`
- Test: `tests/test_models.py`

### Step 1: Write the failing test

Add to `tests/test_models.py`:

```python
def test_optimized_resume_audit_field_optional():
    """OptimizedResume.audit is None by default (v1 path)."""
    resume = OptimizedResume(
        html="<div>test</div>",
        source_checksum="abc123",
    )
    assert resume.audit is None


def test_optimized_resume_audit_field_set():
    """OptimizedResume.audit is populated on the v2 path."""
    from hr_breaker.models.audit import AuditScore
    audit = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Strong",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Strong",
        top_fixes=["fix1", "fix2", "fix3"],
    )
    resume = OptimizedResume(
        html="<div>test</div>",
        source_checksum="abc123",
        audit=audit,
    )
    assert resume.audit is not None
    assert resume.audit.overall == "Strong"
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_models.py::test_optimized_resume_audit_field_optional tests/test_models.py::test_optimized_resume_audit_field_set -v
```

Expected: FAIL with `TypeError` (unexpected keyword argument `audit`)

### Step 3: Modify `src/hr_breaker/models/resume.py`

Add import at the top (after existing imports):

```python
from hr_breaker.models.audit import AuditScore
```

Add field to `OptimizedResume` class after `pdf_path`:

```python
audit: AuditScore | None = None
```

The full `OptimizedResume` class should now end:
```python
    pdf_text: str | None = None
    pdf_bytes: bytes | None = None
    pdf_path: Path | None = None
    audit: AuditScore | None = None
```

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_models.py::test_optimized_resume_audit_field_optional tests/test_models.py::test_optimized_resume_audit_field_set -v
```

Expected: PASS

### Step 5: Run full model test suite to check for regressions

```bash
uv run pytest tests/test_models.py -v
```

Expected: all PASS

### Step 6: Commit

```bash
git add src/hr_breaker/models/resume.py tests/test_models.py
git commit -m "feat: add optional audit field to OptimizedResume"
```

---

## Task 3: Add `optimizer_version` config flag

**Files:**
- Modify: `src/hr_breaker/config.py`
- Test: `tests/test_models.py` (reuse conftest pattern) or new `tests/test_config.py`

### Step 1: Write the failing test

Create `tests/test_config.py`:

```python
"""Tests for config settings."""
import pytest
from unittest.mock import patch


def test_optimizer_version_defaults_to_v1():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {}, clear=False):
        settings = get_settings()
        assert settings.optimizer_version == "v1"
    get_settings.cache_clear()


def test_optimizer_version_reads_from_env():
    from hr_breaker.config import get_settings
    get_settings.cache_clear()
    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v2"}):
        settings = get_settings()
        assert settings.optimizer_version == "v2"
    get_settings.cache_clear()
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'optimizer_version'`

### Step 3: Modify `src/hr_breaker/config.py`

In the `Settings` class, add after `fast_mode`:

```python
optimizer_version: str = "v1"
```

In the `get_settings()` function, add inside the `Settings(...)` constructor call (after `fast_mode=...`):

```python
        optimizer_version=os.getenv("OPTIMIZER_VERSION", "v1"),
```

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_config.py -v
```

Expected: PASS

### Step 5: Commit

```bash
git add src/hr_breaker/config.py tests/test_config.py
git commit -m "feat: add OPTIMIZER_VERSION config flag"
```

---

## Task 4: v2 optimizer agent

**Files:**
- Create: `src/hr_breaker/agents/optimizer_v2.py`
- Modify: `src/hr_breaker/agents/__init__.py`
- Test: `tests/test_optimizer_v2.py`

### Step 1: Write the failing test

Create `tests/test_optimizer_v2.py`:

```python
"""Tests for optimizer v2 agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from hr_breaker.models import ResumeSource, OptimizedResume, JobPosting
from hr_breaker.models.audit import AuditScore
from hr_breaker.models.iteration import IterationContext


@pytest.fixture
def source():
    return ResumeSource(content="Python developer with 5 years experience")


@pytest.fixture
def job():
    return JobPosting(
        title="Senior Python Developer",
        company="Acme",
        requirements=["Python", "FastAPI"],
        keywords=["python", "fastapi", "rest"],
    )


@pytest.fixture
def context(source):
    return IterationContext(
        iteration=0,
        original_resume=source.content,
    )


def test_optimize_resume_v2_returns_optimized_resume_with_audit(source, job, context):
    """optimize_resume_v2 returns OptimizedResume with audit populated."""
    from hr_breaker.agents.optimizer_v2 import OptimizerV2Result
    from hr_breaker.agents import optimize_resume_v2

    mock_audit = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Moderate",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Strong",
        top_fixes=["Add metrics to bullets", "Tighten summary", "Reorder skills"],
    )
    mock_result = OptimizerV2Result(
        html="<header><h1>Test</h1></header>",
        changes=["Rewrote bullets using XYZ formula"],
        audit=mock_audit,
    )

    mock_agent_run = AsyncMock()
    mock_agent_run.return_value.output = mock_result

    with patch("hr_breaker.agents.optimizer_v2.get_optimizer_v2_agent") as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.run = mock_agent_run
        mock_get_agent.return_value = mock_agent

        import asyncio
        result = asyncio.run(optimize_resume_v2(source, job, context))

    assert isinstance(result, OptimizedResume)
    assert result.html == "<header><h1>Test</h1></header>"
    assert result.audit is not None
    assert result.audit.overall == "Strong"
    assert result.audit.ats_compatibility == "ATS-Ready"
    assert result.iteration == 0
```

### Step 2: Run test to verify it fails

```bash
uv run pytest tests/test_optimizer_v2.py -v
```

Expected: FAIL with `ImportError: cannot import name 'optimize_resume_v2'`

### Step 3: Create `src/hr_breaker/agents/optimizer_v2.py`

```python
import logging
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent

from hr_breaker.agents.combined_reviewer import pdf_to_image
from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.filters.data_validator import validate_html
from hr_breaker.filters.keyword_matcher import check_keywords
from hr_breaker.models import (
    IterationContext,
    JobPosting,
    OptimizedResume,
    ResumeSource,
)
from hr_breaker.models.audit import AuditScore
from hr_breaker.services.length_estimator import estimate_content_length
from hr_breaker.services.renderer import HTMLRenderer, RenderError
from hr_breaker.utils import extract_text_from_html

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


def _load_resume_guide() -> str:
    guide_path = TEMPLATE_DIR / "resume_guide.md"
    return guide_path.read_text()


OPTIMIZER_V2_PROMPT = r"""
You are a resume optimization expert applying a structured 8-dimension framework.
Extract content from the user's resume and produce an optimized HTML resume for the job posting.

INPUT: The user's resume text (any format).

OUTPUT: Generate HTML for the <body> of a resume PDF. Do NOT include <html>, <head>, or <body> tags.
Also produce a structured audit score rating the optimized resume across all 8 dimensions.

LANGUAGE RULE (CRITICAL):
- Output MUST be in the SAME LANGUAGE as the original resume
- Never translate regardless of job posting language

STRICT RULES — NEVER VIOLATE:
1. NEVER add technologies, platforms, or tools not in original
2. NEVER fabricate jobs, degrees, certifications, achievements, or metrics
3. NEVER invent metrics or numbers not in original
4. NEVER remove skills or keywords present in the original
5. NEVER use em dash, "delve", "leverage", "robust", or other LLM-generated text markers
6. NEVER add <script> tags
7. NEVER translate the resume

CONTENT BUDGET:
- Target: ~500 words, ~4000 characters (rough estimates; page_count is authoritative)
- Do not return until check_content_length confirms fits_one_page=true

8-DIMENSION OPTIMIZATION — apply each dimension in order:

1. ATS COMPATIBILITY
   - Use standard section headers: "Professional Experience", "Education", "Skills"
   - No tables, columns, text boxes, or graphics
   - Contact info in body (not header/footer of the page)
   - Target role keywords present in resume body, not just skills section

2. RECRUITER SCAN (7-second F-pattern)
   - Name and current title clear and prominent
   - Quantified achievements in the most-scanned position (first bullet of each role)
   - Bullets, not paragraphs
   - Gaps or short tenures present but not over-explained

3. BULLET QUALITY — apply XYZ formula to every bullet
   - XYZ: "Accomplished X measured by Y by doing Z"
   - "So What?" test: each bullet must answer "so what?" at least twice
   - Quantify: hard numbers when available, proxy metrics otherwise
     (e.g. "reduced p95 latency from 800ms to 120ms", "cut review cycle from 3 days to same-day")
   - Vary action verbs — no verb used more than twice across the resume
   - Avoid: "responsible for", "helped with", "worked on"

4. SENIORITY CALIBRATION — match verb tier to candidate's evident level
   - IC:       built / implemented / developed / shipped / debugged
   - Manager:  managed / led / coordinated / hired / grew
   - Director: scaled / established / directed / launched / owned
   - VP+:      championed / orchestrated / transformed / set strategy
   - Impact scope must grow across roles (individual → team → org)

5. KEYWORD COVERAGE
   - Target role keywords from job posting present in resume body
   - Skills ordered by relevance to the job (most relevant first)
   - Specific beats generic ("PostgreSQL, Redis" beats "Databases")

6. STRUCTURE AND LAYOUT
   - Single column only
   - Section order: Summary → Experience → Education → Skills
   - Summary: 2-3 lines, hooks the reader, answers "why this candidate for this role?"
   - Length: 1 page (enforced via check_content_length)

7. CONCERN MANAGEMENT
   - If employment gaps exist: neutral framing, no excuses
   - If short tenures exist: one-line rationale in role description
   - If career switch: bridge sentence connecting past domain to target role

8. CONSISTENCY AND POLISH
   - Current role: present tense; past roles: past tense
   - Punctuation: consistent (all bullets end with period, or none do)
   - No first person ("I led" → "Led")
   - No buzzword padding
   - Dates: consistent format throughout

TOOLS:
- check_content_length(html) — REQUIRED before returning; must confirm fits_one_page=true
- check_keywords_tool(html) — use to verify keyword coverage
- preview_resume(html) — use only if you suspect layout problems
- validate_structure(html) — use after major structural changes

AUDIT:
Rate the OPTIMIZED resume (after your changes) across all 8 dimensions.
Be honest — if a dimension is still Weak after optimization, say so.
top_fixes: list the 3 highest-impact remaining improvements in priority order.
If no concerns exist for concern_management, use "NA".

{resume_guide}
"""


HOW_TO_FIX_FILTERS_V2 = """
HOW TO FIX FAILED FILTERS:
- KeywordMatcher failed → call check_keywords_tool(html). For each missing keyword, search the ORIGINAL resume — if present, surface it in Skills/Summary/relevant bullet. Never invent.
- VectorSimilarityMatcher failed → rephrase Summary and bullet leads with job description terminology. Reorder bullets to lead with most JD-relevant.
- LLMChecker failed → read the issues; usually generic phrasing or LLM-tells. Tighten wording to original tone.
- ContentIntegrityChecker failed → restore removed or paraphrased real facts verbatim.
- DataValidator failed → fix HTML structure. Run validate_structure(html).
- ContentLengthChecker failed → use check_content_length to confirm; trim Summary first, then less-relevant bullets.
"""


class OptimizerV2Result(BaseModel):
    html: str
    changes: list[str]
    audit: AuditScore


def get_optimizer_v2_agent(job: JobPosting, source: ResumeSource) -> Agent:
    """Create optimizer v2 agent with 8-dimension prompt."""
    settings = get_settings()
    resume_guide = _load_resume_guide()
    system_prompt = OPTIMIZER_V2_PROMPT.format(resume_guide=resume_guide)
    agent = Agent(
        f"google-gla:{settings.gemini_pro_model}",
        output_type=OptimizerV2Result,
        system_prompt=system_prompt,
        model_settings=get_model_settings(),
    )

    @agent.system_prompt
    def add_current_date() -> str:
        return f"Today's date: {date.today().strftime('%B %Y')}"

    _length_cache: dict[str, dict] = {}

    @agent.tool_plain
    def check_content_length(html: str) -> dict:
        """Check if HTML content fits one page by rendering PDF."""
        cached = _length_cache.get(html)
        if cached is not None:
            logger.debug("check_content_length cache hit")
            return cached

        est = estimate_content_length(html)
        try:
            renderer = HTMLRenderer()
            render_result = renderer.render(html)
            page_count = render_result.page_count
            fits_one_page = page_count == 1
        except RenderError as e:
            err_result = {
                "fits_one_page": False,
                "error": f"Render failed: {e}",
                "estimates": {"chars": est.chars, "words": est.words},
            }
            _length_cache[html] = err_result
            return err_result

        result = {
            "fits_one_page": fits_one_page,
            "page_count": page_count,
            "estimates": {
                "chars": est.chars,
                "words": est.words,
                "limits": {"chars": settings.resume_max_chars, "words": settings.resume_max_words},
            },
        }
        if not fits_one_page:
            result["suggestion"] = f"Content spans {page_count} pages. Remove ~{est.overflow_words} words (estimate)"
        _length_cache[html] = result
        return result

    @agent.tool_plain
    def preview_resume(html: str) -> BinaryContent:
        """Render HTML to PDF and return preview image."""
        renderer = HTMLRenderer()
        result = renderer.render(html)
        image_bytes, _ = pdf_to_image(result.pdf_bytes)
        return BinaryContent(data=image_bytes, media_type="image/png")

    @agent.tool_plain
    def check_keywords_tool(html: str) -> dict:
        """Check keyword coverage vs job posting."""
        resume_text = extract_text_from_html(html)
        result = check_keywords(resume_text, job)
        return {
            "passed": result.passed,
            "score": round(result.score, 2),
            "missing_keywords": result.missing_keywords,
        }

    @agent.tool_plain
    def validate_structure(html: str) -> dict:
        """Check HTML structure."""
        valid, issues = validate_html(html)
        return {"valid": valid, "issues": issues}

    return agent


async def optimize_resume_v2(
    source: ResumeSource,
    job: JobPosting,
    context: IterationContext,
) -> OptimizedResume:
    """Optimize resume using the 8-dimension approach."""
    prompt = f"""## Original Resume:
{context.original_resume}

## Job Posting:
Title: {job.title}
Company: {job.company}
Requirements: {', '.join(job.requirements)}
Keywords: {', '.join(job.keywords)}
Description: {job.description}
"""

    if context.last_attempt:
        estimate = estimate_content_length(context.last_attempt)
        prompt += f"""
## Last Attempt (Iteration {context.iteration}):
{context.last_attempt}

## Current Content Stats:
- Current: {estimate.chars} chars, {estimate.words} words

NOTE: This is a REFINEMENT iteration. Make the smallest possible change to pass failed filters.
"""

    if context.validation:
        prompt += f"""
## Filter Results:
{context.format_filter_results()}
{HOW_TO_FIX_FILTERS_V2}
IMPORTANT: Make MINIMAL changes to fix ONLY the failed filters.
"""

    prompt += """
Return JSON with:
- html: The HTML body content (no wrapper tags)
- changes: List of changes made
- audit: Audit scores for all 8 dimensions of the OPTIMIZED resume

Output ONLY valid JSON.
"""

    agent = get_optimizer_v2_agent(job, source)
    result = await agent.run(prompt)
    return OptimizedResume(
        html=result.output.html,
        iteration=context.iteration,
        changes=result.output.changes,
        source_checksum=source.checksum,
        audit=result.output.audit,
    )
```

### Step 4: Export from `src/hr_breaker/agents/__init__.py`

Add import:
```python
from .optimizer_v2 import optimize_resume_v2
```

Add `"optimize_resume_v2"` to `__all__`.

### Step 5: Run test to verify it passes

```bash
uv run pytest tests/test_optimizer_v2.py -v
```

Expected: PASS

### Step 6: Commit

```bash
git add src/hr_breaker/agents/optimizer_v2.py src/hr_breaker/agents/__init__.py tests/test_optimizer_v2.py
git commit -m "feat: add optimizer v2 agent with 8-dimension prompt"
```

---

## Task 5: Orchestration routing

**Files:**
- Modify: `src/hr_breaker/orchestration.py`
- Test: `tests/test_orchestration.py`

### Step 1: Write the failing test

Add to `tests/test_orchestration.py`:

```python
from unittest.mock import patch, AsyncMock
from hr_breaker.models.audit import AuditScore


@pytest.mark.asyncio
async def test_optimize_for_job_uses_v1_by_default(source_resume, job_posting):
    """When OPTIMIZER_VERSION is not set, uses optimize_resume (v1)."""
    from hr_breaker.orchestration import optimize_for_job
    from hr_breaker.config import get_settings
    get_settings.cache_clear()

    mock_optimized = OptimizedResume(
        html="<div>v1 result</div>",
        source_checksum=source_resume.checksum,
        pdf_text="v1 text",
        pdf_bytes=b"%PDF-1.4",
    )

    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v1"}):
        get_settings.cache_clear()
        with patch("hr_breaker.orchestration.optimize_resume", new_callable=AsyncMock, return_value=mock_optimized) as mock_v1, \
             patch("hr_breaker.orchestration.optimize_resume_v2", new_callable=AsyncMock) as mock_v2, \
             patch("hr_breaker.orchestration._render_and_extract", return_value=mock_optimized), \
             patch("hr_breaker.orchestration.run_filters", new_callable=AsyncMock) as mock_filters:
            from hr_breaker.models import ValidationResult
            mock_filters.return_value = ValidationResult(results=[])
            await optimize_for_job(source=source_resume, job=job_posting, max_iterations=1)
            mock_v1.assert_called_once()
            mock_v2.assert_not_called()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_optimize_for_job_uses_v2_when_flag_set(source_resume, job_posting):
    """When OPTIMIZER_VERSION=v2, uses optimize_resume_v2."""
    from hr_breaker.orchestration import optimize_for_job
    from hr_breaker.config import get_settings

    audit = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Strong",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Strong",
        top_fixes=["fix1", "fix2", "fix3"],
    )
    mock_optimized = OptimizedResume(
        html="<div>v2 result</div>",
        source_checksum=source_resume.checksum,
        pdf_text="v2 text",
        pdf_bytes=b"%PDF-1.4",
        audit=audit,
    )

    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v2"}):
        get_settings.cache_clear()
        with patch("hr_breaker.orchestration.optimize_resume", new_callable=AsyncMock) as mock_v1, \
             patch("hr_breaker.orchestration.optimize_resume_v2", new_callable=AsyncMock, return_value=mock_optimized) as mock_v2, \
             patch("hr_breaker.orchestration._render_and_extract", return_value=mock_optimized), \
             patch("hr_breaker.orchestration.run_filters", new_callable=AsyncMock) as mock_filters:
            from hr_breaker.models import ValidationResult
            mock_filters.return_value = ValidationResult(results=[])
            result_optimized, _, _ = await optimize_for_job(source=source_resume, job=job_posting, max_iterations=1)
            mock_v2.assert_called_once()
            mock_v1.assert_not_called()
            assert result_optimized.audit is not None
    get_settings.cache_clear()
```

### Step 2: Run tests to verify they fail

```bash
uv run pytest tests/test_orchestration.py::test_optimize_for_job_uses_v1_by_default tests/test_orchestration.py::test_optimize_for_job_uses_v2_when_flag_set -v
```

Expected: FAIL with `ImportError` or assertion errors

### Step 3: Modify `src/hr_breaker/orchestration.py`

Change the import at line 10:
```python
from hr_breaker.agents import optimize_resume, optimize_resume_v2, parse_job_posting
```

Replace lines 158-159 inside the `for i in range(max_iterations):` loop:
```python
        with log_time("optimize_resume (LLM)"):
            optimized = await optimize_resume(source, job, ctx)
```

With:
```python
        with log_time("optimize_resume (LLM)"):
            if settings.optimizer_version == "v2":
                optimized = await optimize_resume_v2(source, job, ctx)
            else:
                optimized = await optimize_resume(source, job, ctx)
```

Add `settings = get_settings()` at the top of `optimize_for_job()` (line 129, right after the docstring), since `settings` is already used for `max_iterations` there — confirm it is already set, if not add it.

### Step 4: Run tests to verify they pass

```bash
uv run pytest tests/test_orchestration.py::test_optimize_for_job_uses_v1_by_default tests/test_orchestration.py::test_optimize_for_job_uses_v2_when_flag_set -v
```

Expected: PASS

### Step 5: Run full orchestration test suite

```bash
uv run pytest tests/test_orchestration.py -v
```

Expected: all PASS

### Step 6: Commit

```bash
git add src/hr_breaker/orchestration.py tests/test_orchestration.py
git commit -m "feat: route to optimizer v2 when OPTIMIZER_VERSION=v2"
```

---

## Task 6: Save audit in API response

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py`
- Test: `tests/test_optimize_routes.py`

### Step 1: Check existing test for the complete optimization route

Open `tests/test_optimize_routes.py` and find the test that checks the result saved to Supabase (the `update_optimization_run` call in `_run_optimization`). Note the shape of the dict it expects.

### Step 2: Write the failing test

Add to `tests/test_optimize_routes.py` (or as a standalone test function, following the pattern in the file):

```python
def test_run_optimization_saves_audit_when_v2(...)
    """When optimizer v2 produces an audit, it is saved to Supabase."""
    # Follow the existing mock pattern in the file.
    # Key assertion: supabase.update_optimization_run was called with a dict
    # containing "audit" key that is not None when optimized.audit is set.
```

Look at the existing test structure first — if tests mock `optimize_for_job`, add an `audit` field to the mock return value and assert it flows through.

### Step 3: Modify `src/hr_breaker/api/routes/optimize.py`

In `_run_optimization()`, find the final `supabase.update_optimization_run` call (around line 200) and add the audit field:

```python
        supabase.update_optimization_run(run_id, {
            "status": "complete",
            "current_step": None,
            "result_html": result_html,
            "result_pdf_path": result_pdf_path,
            "feedback": all_feedback,
            "timing": timing,
            "audit": optimized.audit.model_dump() if optimized and optimized.audit else None,
        })
```

No other changes needed — the GET `/{run_id}` endpoint reads the full record from Supabase, so `audit` will appear in the response automatically once it is stored.

### Step 4: Run the test to verify it passes

```bash
uv run pytest tests/test_optimize_routes.py -v
```

Expected: all PASS

### Step 5: Run full test suite

```bash
uv run pytest -v
```

Expected: all PASS (or same failures as before this change)

### Step 6: Commit

```bash
git add src/hr_breaker/api/routes/optimize.py tests/test_optimize_routes.py
git commit -m "feat: persist audit score in optimization run result"
```

---

## Done — How to test end-to-end

1. Set `OPTIMIZER_VERSION=v2` in your `.env`
2. Run the backend: `uv run uvicorn hr_breaker.api.main:app --reload`
3. Submit an optimization via the frontend
4. Check the result — the API response will include `audit: { ats_compatibility, recruiter_scan, ... }`
5. Switch back to `OPTIMIZER_VERSION=v1` and run again — `audit` will be `null`, all other behavior identical

To compare both optimizers on the same resume+job, run twice: once with `v1`, once with `v2`. The PDF output and filter scores are directly comparable.
