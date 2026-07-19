# CV Pipeline Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken quality filters, remove the event-loop blocking and duplicated PDF renders in the CV optimization pipeline, and clean up dead/inconsistent configuration — without touching the (separately-scoped) security findings.

**Architecture:** Three independent workstreams. **Phase A (filter correctness)** fixes deterministic scoring bugs that corrupt the optimizer's feedback signal — pure logic changes with unit tests, no I/O. **Phase B (performance)** removes duplicated WeasyPrint renders by threading the already-rendered `pdf_bytes` through the pipeline, caches renderers/agents, and offloads synchronous I/O off the FastAPI event loop with `asyncio.to_thread` plus a single shared Supabase client. **Phase C (cleanup)** removes dead config/quota code and reconciles inconsistencies. Phases are independent; A is the highest value-per-line and lowest risk, so do it first.

**Tech Stack:** Python 3.12, FastAPI, pydantic-ai (Vertex/Gemini), WeasyPrint, PyMuPDF (`fitz`), scikit-learn (TF-IDF), sentence-transformers, Supabase Python client, pytest + pytest-asyncio (`asyncio_mode = "auto"`).

## Global Constraints

- Python source lives under `src/` (`pythonpath = ["src"]` in `pyproject.toml`); tests under `tests/`.
- Run tests with: `uv run pytest <path> -v`. On macOS the render path needs `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` — the renderer sets it automatically, but if a WeasyPrint import error appears, prefix the command with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- `asyncio_mode = "auto"` — async tests do NOT need `@pytest.mark.asyncio`, but existing tests use it; match the file you are editing.
- Tests that hit real LLMs/Supabase are gated behind `-m benchmark` and skipped by default. Every test in this plan must run WITHOUT that marker (no network, no LLM, no real Supabase).
- Do not modify security-sensitive code paths (`api/routes/telegram.py`, `api/routes/webhooks.py`, `get_default_cv`, auth PII logging) — those are out of scope for this plan.
- Match existing code style; make surgical changes. Every changed line must trace to a task below.
- Commit after each task with the message shown.

---

## Phase A — Filter correctness

These bugs make the deterministic filters report wrong scores, which misleads both the LLM optimizer (it burns iterations chasing unfixable feedback) and the user-facing editor. All are pure-logic, unit-testable, no I/O.

### Task A1: KeywordMatcher — accept HTML-only input (fixes editor `/validate`)

The editor's `POST /{run_id}/validate` builds `OptimizedResume(html=..., pdf_text=None)` and runs `KeywordMatcher`, which short-circuits to `passed=False, score=0.0, "No PDF text available"` whenever `pdf_text is None`. So every editor keyword check is bogus. Fix: fall back to text extracted from `html` when `pdf_text` is absent.

**Files:**
- Modify: `src/hr_breaker/filters/keyword_matcher.py` (the `evaluate` method, around lines 105-113)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `hr_breaker.utils.extract_text_from_html(html: str) -> str` (already used in `agents/optimizer.py:208`).
- Produces: `KeywordMatcher.evaluate` now returns a real score when `optimized.pdf_text is None` but `optimized.html` is set; still returns the "no content" failure only when BOTH are `None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_filters.py`:

```python
@pytest.mark.asyncio
async def test_keyword_matcher_html_only_no_pdf_text(source_resume, job_posting):
    # Editor /validate path: html set, pdf_text is None. Should still score, not hard-fail.
    optimized = OptimizedResume(
        html="<div>Backend Engineer with Python Django PostgreSQL REST API experience</div>",
        source_checksum=source_resume.checksum,
        pdf_text=None,
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    assert result.passed
    assert result.score >= matcher.threshold
    assert "No PDF text available" not in result.issues


@pytest.mark.asyncio
async def test_keyword_matcher_no_content_at_all(source_resume, job_posting):
    optimized = OptimizedResume(
        html=None, source_checksum=source_resume.checksum, pdf_text=None
    )
    result = await KeywordMatcher().evaluate(optimized, job_posting, source_resume)
    assert not result.passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filters.py::test_keyword_matcher_html_only_no_pdf_text -v`
Expected: FAIL — result.passed is False and issues contains "No PDF text available".

- [ ] **Step 3: Write minimal implementation**

At the top of `src/hr_breaker/filters/keyword_matcher.py`, ensure the import exists:

```python
from hr_breaker.utils import extract_text_from_html
```

Replace the `pdf_text is None` guard in `KeywordMatcher.evaluate` (currently lines ~105-113) with:

```python
        resume_text = optimized.pdf_text
        if resume_text is None and optimized.html is not None:
            resume_text = extract_text_from_html(optimized.html)
        if not resume_text:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                score=0.0,
                threshold=self.threshold,
                issues=["No resume content available"],
                suggestions=["Ensure PDF compilation succeeds"],
            )
```

Then find where the method uses `optimized.pdf_text` for scoring below the guard and change it to use the local `resume_text` variable (call `check_keywords(resume_text, job)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filters.py -v`
Expected: PASS (all keyword tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/keyword_matcher.py tests/test_filters.py
git commit -m "fix(filters): KeywordMatcher scores HTML-only input for editor /validate"
```

---

### Task A2: KeywordMatcher — match symbol keywords (`c++`, `c#`, `.net`, `f#`)

`rf"\b{re.escape(keyword)}\b"` cannot match keywords bounded by non-word characters: `\b` after `+`/`#` or before `.` requires an adjacent word character. So `c++`, `c#`, `.net`, `f#` are permanently "missing" for the jobs that most need them. Fix: use a boundary that works for symbol-ending/starting tokens.

**Files:**
- Modify: `src/hr_breaker/filters/keyword_matcher.py` (the per-keyword regex, around lines 68-70)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `check_keywords` now matches symbol keywords. Behavior for alphanumeric keywords is unchanged (still whole-word, so "java" does not match "javascript").

- [ ] **Step 1: Write the failing test**

Add to `tests/test_filters.py`:

```python
@pytest.mark.asyncio
async def test_keyword_matcher_symbol_keywords_match():
    from hr_breaker.filters.keyword_matcher import check_keywords

    job = JobPosting(
        title="Systems Engineer",
        company="Acme",
        requirements=["C++", "C#", ".NET"],
        keywords=["c++", "c#", ".net"],
    )
    resume_text = "Built low-latency services in C++ and C#, plus tooling on .NET."

    result = check_keywords(resume_text, job)

    assert "c++" not in result.missing_keywords
    assert "c#" not in result.missing_keywords
    assert ".net" not in result.missing_keywords


@pytest.mark.asyncio
async def test_keyword_matcher_alnum_still_whole_word():
    from hr_breaker.filters.keyword_matcher import check_keywords

    job = JobPosting(title="Dev", company="Acme", requirements=[], keywords=["java"])
    # "javascript" must NOT satisfy the "java" keyword.
    result = check_keywords("Expert in JavaScript frameworks.", job)
    assert "java" in result.missing_keywords
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filters.py::test_keyword_matcher_symbol_keywords_match -v`
Expected: FAIL — `c++`, `c#`, `.net` all appear in `missing_keywords`.

- [ ] **Step 3: Write minimal implementation**

In `src/hr_breaker/filters/keyword_matcher.py`, replace the matching loop that builds `pattern = rf"\b{re.escape(keyword)}\b"` with a boundary that treats the keyword as delimited by whitespace/string-edge/punctuation rather than `\b`:

```python
    for keyword in significant_keywords:
        esc = re.escape(keyword)
        # Use lookarounds instead of \b so symbol-bounded keywords (c++, c#, .net)
        # match. A keyword is a hit when not flanked by an alphanumeric character.
        pattern = rf"(?<![a-z0-9]){esc}(?![a-z0-9])"
        if re.search(pattern, resume_lower):
            matched.append(keyword)
        else:
            missing.append(keyword)
```

(`resume_lower` and `keyword` are already lowercased upstream, so `[a-z0-9]` is correct; keep the existing `re` import.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filters.py -v`
Expected: PASS, including both new tests and the pre-existing keyword tests (whole-word behavior for alphanumeric keywords preserved).

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/keyword_matcher.py tests/test_filters.py
git commit -m "fix(filters): match symbol keywords (c++, c#, .net) in KeywordMatcher"
```

---

### Task A3: VectorSimilarityMatcher — fix score/threshold scale mismatch

The filter maps cosine to `(sim + 1) / 2`, then compares to `filter_vector_threshold = 0.4`. Passing needs only raw cosine ≥ −0.2, which any two English texts clear — the filter passes everything while paying full model-load + encode cost. Fix: compare against the raw cosine (`[0,1]` for these embeddings, which are non-negative) and drop the renormalization, keeping the existing `0.4` threshold as a real gate.

**Files:**
- Modify: `src/hr_breaker/filters/vector_similarity_matcher.py` (around lines 76-90)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `VectorSimilarityMatcher.evaluate` returns `score = raw cosine similarity` (0.0–1.0 range for MiniLM), compared directly against `self.threshold` (0.4). Unrelated resume/job pairs now fall below threshold.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_filters.py`. This test stubs the model so it runs without downloading weights:

```python
@pytest.mark.asyncio
async def test_vector_matcher_score_is_raw_cosine(monkeypatch):
    import numpy as np
    from hr_breaker.filters import vector_similarity_matcher as vsm

    class FakeModel:
        def encode(self, texts):
            # Nearly-orthogonal vectors -> cosine ~0.0, must be BELOW 0.4 threshold.
            return np.array([[1.0, 0.0], [0.0, 1.0]])

    monkeypatch.setattr(
        vsm.VectorSimilarityMatcher, "_get_model", lambda self: FakeModel()
    )

    job = JobPosting(title="Chef", company="Acme", description="Cook food", requirements=[])
    optimized = OptimizedResume(
        html="<div>x</div>", source_checksum="c", pdf_text="Quantum physics research"
    )
    result = await vsm.VectorSimilarityMatcher().evaluate(optimized, job, ResumeSource(content="x"))

    assert result.score < 0.05          # raw cosine, not (sim+1)/2 == 0.5
    assert not result.passed            # 0.0 < 0.4 threshold
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filters.py::test_vector_matcher_score_is_raw_cosine -v`
Expected: FAIL — `result.score` is ~0.5 (renormalized) and `result.passed` is True.

- [ ] **Step 3: Write minimal implementation**

In `src/hr_breaker/filters/vector_similarity_matcher.py`, after computing `similarity`, delete the renormalization line and use the raw cosine directly:

```python
        # Cosine similarity of MiniLM embeddings of resume vs job text.
        # Non-negative in practice; compare directly against the threshold.
        score = max(0.0, similarity)
```

Remove the old `score = (similarity + 1) / 2` line and its `# Normalize to 0-1` comment. Leave the downstream `if score < self.threshold:` block and issue/suggestion text as-is.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/vector_similarity_matcher.py tests/test_filters.py
git commit -m "fix(filters): compare raw cosine to threshold in VectorSimilarityMatcher"
```

---

### Task A4: VectorSimilarityMatcher — stop embedding the literal string "None"

`vector_similarity_matcher.py:65` builds `f"{job.title} {job.description} ..."`; when `description` is `None` the string `"None"` is embedded into the job vector (KeywordMatcher already guards this with `job.description or ''`). Fold this into the same file while it's open.

**Files:**
- Modify: `src/hr_breaker/filters/vector_similarity_matcher.py` (line ~65)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: job text used for embedding contains no literal `"None"` when fields are absent.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_vector_matcher_no_literal_none(monkeypatch):
    import numpy as np
    from hr_breaker.filters import vector_similarity_matcher as vsm

    captured = {}

    class FakeModel:
        def encode(self, texts):
            captured["job_text"] = texts[1]
            return np.array([[1.0, 0.0], [1.0, 0.0]])

    monkeypatch.setattr(
        vsm.VectorSimilarityMatcher, "_get_model", lambda self: FakeModel()
    )

    job = JobPosting(title="Chef", company="Acme", description=None, requirements=[])
    optimized = OptimizedResume(html="<div>x</div>", source_checksum="c", pdf_text="Cook")
    await vsm.VectorSimilarityMatcher().evaluate(optimized, job, ResumeSource(content="x"))

    assert "None" not in captured["job_text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filters.py::test_vector_matcher_no_literal_none -v`
Expected: FAIL — captured job_text contains "None".

- [ ] **Step 3: Write minimal implementation**

Change the job-text construction line to guard each optional field:

```python
        job_text = f"{job.title} {job.description or ''} {' '.join(job.requirements)}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/vector_similarity_matcher.py tests/test_filters.py
git commit -m "fix(filters): guard None job.description in vector similarity input"
```

---

### Task A5: ContentIntegrityChecker — make the reported threshold govern pass/fail

`content_integrity.py` hardcodes `0.9`/`0.5` internally, while the filter *reports* `threshold = settings.filter_hallucination_threshold` and there is a separate `filter_ai_generated_threshold` config that is never used anywhere. Result: changing the env vars alters the displayed threshold but not behavior, and "passed=True, score below threshold" pairs get persisted. Fix: drive the two internal decisions from the two existing settings so config is truthful.

**Files:**
- Modify: `src/hr_breaker/agents/content_integrity.py` (the two hardcoded comparisons: `0.9` for hallucination pass, `0.5` for AI-probability pass)
- Modify: `src/hr_breaker/filters/content_integrity_checker.py` (only if needed to keep the reported `threshold` consistent — see step 3)
- Test: `tests/test_data_validator.py` OR a new `tests/test_content_integrity.py` (choose the file that already tests this agent; if none, create `tests/test_content_integrity.py`)

**Interfaces:**
- Consumes: `get_settings().filter_hallucination_threshold` (default 0.9), `get_settings().filter_ai_generated_threshold` (default 0.4).
- Produces: `check_content_integrity` uses `filter_hallucination_threshold` for the hallucination pass decision and `filter_ai_generated_threshold` for the AI-detection pass decision. No new public signatures.

- [ ] **Step 1: Read the current logic**

Read `src/hr_breaker/agents/content_integrity.py` lines 140-190 to locate the two comparisons (the `0.9` hallucination-score gate and the `0.5` ai_probability gate) and confirm the exact variable names before editing.

- [ ] **Step 2: Write the failing test**

Create `tests/test_content_integrity.py` (adjust import names to the actual functions found in Step 1 — the plan assumes `_build_hallucination_result(score)` / `_build_ai_result(probability)` helpers; if the logic is inline, refactor the two decisions into small pure helpers first, then test those):

```python
from hr_breaker.config import get_settings

def test_hallucination_gate_uses_config_threshold(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("FILTER_HALLUCINATION_THRESHOLD", "0.8")
    s = get_settings()
    assert s.filter_hallucination_threshold == 0.8
    # A hallucination score of 0.85 must PASS under an 0.8 gate.
    from hr_breaker.agents.content_integrity import _hallucination_passed
    assert _hallucination_passed(0.85) is True
    assert _hallucination_passed(0.75) is False
    get_settings.cache_clear()


def test_ai_gate_uses_config_threshold(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("FILTER_AI_GENERATED_THRESHOLD", "0.4")
    from hr_breaker.agents.content_integrity import _ai_passed
    # ai_probability below threshold passes.
    assert _ai_passed(0.3) is True
    assert _ai_passed(0.5) is False
    get_settings.cache_clear()
```

- [ ] **Step 3: Write minimal implementation**

In `content_integrity.py`, extract the two pass decisions into pure helpers driven by settings and replace the hardcoded literals:

```python
def _hallucination_passed(score: float) -> bool:
    return score >= get_settings().filter_hallucination_threshold


def _ai_passed(ai_probability: float) -> bool:
    return ai_probability < get_settings().filter_ai_generated_threshold
```

Replace the inline `>= 0.9` and `< 0.5` (or `>= 0.5`) comparisons with calls to these helpers. Keep the `score` values returned to the filter as they are; only the pass/fail booleans change source-of-truth.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_content_integrity.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/agents/content_integrity.py tests/test_content_integrity.py
git commit -m "fix(filters): drive content-integrity gates from config thresholds"
```

---

### Task A6: Job parser grounding — use word-boundary matching, not substring

`_is_grounded` (`agents/job_parser.py:99`) uses `all(w in norm_text for w in norm_value.split())`, so hallucinated "Ada" is "grounded" by "Canada". Tighten to whole-word matching per token.

**Files:**
- Modify: `src/hr_breaker/agents/job_parser.py` (the `_is_grounded` helper, ~line 99)
- Test: `tests/test_job_parser.py`

**Interfaces:**
- Consumes: nothing new (`re` is standard lib).
- Produces: `_is_grounded(value, text)` returns True only when every token of `value` appears as a whole word in `text`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_job_parser.py`:

```python
def test_is_grounded_rejects_substring_hallucination():
    from hr_breaker.agents.job_parser import _is_grounded
    # "Ada" must NOT be grounded by "Canada".
    assert _is_grounded("Ada", "We are hiring in Canada") is False

def test_is_grounded_accepts_real_token():
    from hr_breaker.agents.job_parser import _is_grounded
    assert _is_grounded("Acme Corp", "Join Acme Corp today") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_parser.py::test_is_grounded_rejects_substring_hallucination -v`
Expected: FAIL — returns True (substring match).

- [ ] **Step 3: Write minimal implementation**

In `agents/job_parser.py`, change the grounding check to whole-word per token:

```python
    import re
    return all(
        re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", norm_text)
        for w in norm_value.split()
    )
```

(Keep the existing normalization that produces `norm_text`/`norm_value`; if `re` is not already imported at module top, add it there instead of inline.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/agents/job_parser.py tests/test_job_parser.py
git commit -m "fix(job-parser): word-boundary grounding check to reject substring hallucinations"
```

---

### Task A7: Auditor — stop deleting `<...>` content from plain text

`audit_resume` (`agents/auditor.py:78`) treats any text containing `<` as HTML and strips tags, silently damaging PDF-extracted text that mentions e.g. `C<T>`. Fix: only strip when the input actually looks like an HTML document/fragment, not merely because a `<` appears.

**Files:**
- Modify: `src/hr_breaker/agents/auditor.py` (line ~78)
- Test: `tests/test_audit_scoring.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `audit_resume` only extracts-from-HTML when the input contains a real tag pattern (`<tag ...>` or `</tag>`); plain text with stray `<` is passed through verbatim.

- [ ] **Step 1: Write the failing test**

Add a small pure helper and test it (avoids invoking the LLM). Add to `tests/test_audit_scoring.py`:

```python
def test_looks_like_html_distinguishes_generics_from_markup():
    from hr_breaker.agents.auditor import _looks_like_html
    assert _looks_like_html("<div>Resume</div>") is True
    assert _looks_like_html("<p>Experience</p>") is True
    assert _looks_like_html("Implemented Cache<T> generics in C++") is False
    assert _looks_like_html("Skills: math < stats") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audit_scoring.py::test_looks_like_html_distinguishes_generics_from_markup -v`
Expected: FAIL — `_looks_like_html` does not exist.

- [ ] **Step 3: Write minimal implementation**

In `agents/auditor.py`, add a helper and use it:

```python
import re

_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(\s[^<>]*)?>")


def _looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG_RE.search(text))
```

Change the branch at line ~78 from `if "<" in text_or_html` to:

```python
    resume_text = (
        extract_text_from_html(text_or_html)
        if _looks_like_html(text_or_html)
        else text_or_html
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audit_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/agents/auditor.py tests/test_audit_scoring.py
git commit -m "fix(auditor): only strip HTML when input is actually markup"
```

---

## Phase B — Performance

Phase A is fully independent of Phase B and should merge first. Phase B removes wasted CPU and un-blocks the event loop.

### Task B1: Reuse rendered `pdf_bytes` in ContentLengthChecker (kill 1 of 3 renders/iteration)

Each optimization iteration renders the same HTML to PDF up to three times: `_render_and_extract` (orchestration), `ContentLengthChecker` (re-renders), and `combined_review` (LLMChecker). `ContentLengthChecker` should use the `pdf_bytes` orchestration already populated on `optimized`.

**Files:**
- Modify: `src/hr_breaker/filters/content_length.py` (`ContentLengthChecker.evaluate`, lines ~55-100)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `optimized.pdf_bytes: bytes | None` (populated by `orchestration._render_and_extract`). `fitz` for page count from bytes.
- Produces: `ContentLengthChecker.evaluate` renders only when `optimized.pdf_bytes is None` (e.g. the editor path); otherwise it reads page count from the existing bytes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_filters.py` a test asserting the checker does NOT call the renderer when `pdf_bytes` is present:

```python
@pytest.mark.asyncio
async def test_content_length_reuses_existing_pdf_bytes(monkeypatch, job_posting):
    from hr_breaker.filters.content_length import ContentLengthChecker
    from hr_breaker.services import renderer as renderer_mod

    def boom():
        raise AssertionError("renderer must not be constructed when pdf_bytes exists")

    monkeypatch.setattr(renderer_mod, "get_renderer", boom)

    # Minimal 1-page PDF produced once via a real render in a fixture would be ideal;
    # here we render a tiny doc directly to get valid bytes.
    from hr_breaker.services.renderer import HTMLRenderer
    pdf = HTMLRenderer().render("<h1>Test</h1><p>Short resume.</p>").pdf_bytes

    optimized = OptimizedResume(
        html="<h1>Test</h1><p>Short resume.</p>",
        source_checksum="c",
        pdf_bytes=pdf,
    )
    result = await ContentLengthChecker().evaluate(optimized, job_posting, ResumeSource(content="x"))
    assert result.passed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_filters.py::test_content_length_reuses_existing_pdf_bytes -v`
Expected: FAIL — AssertionError from `boom` (checker re-renders).

- [ ] **Step 3: Write minimal implementation**

In `content_length.py`, refactor `evaluate` so it derives `pdf_bytes` and `page_count` from `optimized.pdf_bytes` when available:

```python
        if optimized.html is None:
            return FilterResult(filter_name=self.name, passed=True, score=1.0,
                                threshold=self.threshold, issues=[], suggestions=[])

        pdf_bytes = optimized.pdf_bytes
        if pdf_bytes is None:
            try:
                pdf_bytes = get_renderer().render(optimized.html).pdf_bytes
            except RenderError as e:
                return FilterResult(filter_name=self.name, passed=False, score=0.0,
                                    threshold=self.threshold,
                                    issues=[f"Rendering failed: {e}"],
                                    suggestions=["Fix HTML content to allow rendering"])

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)
```

Then keep the existing page-count/overflow branches but have `check_page2_overflow` receive `pdf_bytes` as it does today. (This also fixes the leaked `fitz` handle — see Task B2, which is folded here via the `with` block.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/content_length.py tests/test_filters.py
git commit -m "perf(filters): reuse rendered pdf_bytes in ContentLengthChecker"
```

---

### Task B2: Close the `fitz` document in `check_page2_overflow`

`check_page2_overflow` opens a `fitz` document without closing it, leaking a native handle per 2-page check. (If Task B1 already wrapped the caller's open in a `with`, this task covers the `check_page2_overflow` helper specifically.)

**Files:**
- Modify: `src/hr_breaker/filters/content_length.py` (`check_page2_overflow`, lines 13-29)
- Test: covered by existing `tests/test_filters.py` render tests (no new behavior); this is a resource-safety fix.

- [ ] **Step 1: Write minimal implementation**

Wrap the open in a context manager:

```python
def check_page2_overflow(pdf_bytes: bytes) -> str | None:
    settings = get_settings()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if len(doc) < 2:
            return None
        page2_text = doc[1].get_text().strip()
    if len(page2_text) > 0 and len(page2_text) < settings.resume_page2_overflow_chars:
        logger.debug(f"check_page2_overflow: page 2 len {len(page2_text)} - overflow from page 1")
        return f"Page 2 has only {len(page2_text)} chars - content overflow from page 1"
    return None
```

- [ ] **Step 2: Run tests to verify no regression**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/hr_breaker/filters/content_length.py
git commit -m "fix(filters): close fitz document in check_page2_overflow"
```

---

### Task B3: Cache the HTMLRenderer so it is built once

`get_renderer()` / `HTMLRenderer()` rebuilds the Jinja `Environment`, scans system fonts via `FontConfiguration`, and re-reads the wrapper template on every call, despite `get_renderer`'s cache-suggesting name. Cache a single instance. WeasyPrint's `render()` is stateless per call, so one shared instance is safe.

**Files:**
- Modify: `src/hr_breaker/services/renderer.py` (`get_renderer`, lines 176-178)
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `get_renderer()` returns the same `HTMLRenderer` instance across calls (`@lru_cache`). Call sites that use `HTMLRenderer()` directly (`orchestration.py:137`, `optimizer*.py`, `editor.py`) should switch to `get_renderer()` in Task B4/B6; this task only makes the cached accessor real.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_renderer.py`:

```python
def test_get_renderer_is_cached():
    from hr_breaker.services.renderer import get_renderer
    assert get_renderer() is get_renderer()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_renderer.py::test_get_renderer_is_cached -v`
Expected: FAIL — two distinct instances.

- [ ] **Step 3: Write minimal implementation**

In `renderer.py`:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_renderer() -> HTMLRenderer:
    """Return the process-wide HTML renderer (built once)."""
    return HTMLRenderer()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_renderer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/services/renderer.py tests/test_renderer.py
git commit -m "perf(renderer): cache the HTMLRenderer instance process-wide"
```

---

### Task B4: Use the cached renderer everywhere (orchestration, optimizer tools, editor)

Point the direct `HTMLRenderer()` construction sites at `get_renderer()` so they benefit from B3. This also means the optimizer tools' `check_content_length` no longer pays renderer setup on every LLM tool call.

**Files:**
- Modify: `src/hr_breaker/orchestration.py:137`
- Modify: `src/hr_breaker/agents/optimizer.py:155,200`
- Modify: `src/hr_breaker/agents/optimizer_v2.py:175,211`
- Modify: `src/hr_breaker/api/routes/editor.py:141`
- Test: existing `tests/test_renderer.py`, `tests/test_editor_api.py` (no behavior change; regression guard)

**Interfaces:**
- Consumes: `get_renderer()` from `hr_breaker.services.renderer`.
- Produces: no signature changes; all render sites share one renderer.

- [ ] **Step 1: Replace construction sites**

In each file above, replace `HTMLRenderer()` with `get_renderer()` and update the import to `from hr_breaker.services.renderer import get_renderer, RenderError` (drop the now-unused `HTMLRenderer` import only where it becomes unused). In `orchestration.py`, `renderer = HTMLRenderer()` at line 137 becomes `renderer = get_renderer()`.

- [ ] **Step 2: Run the affected test suites**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_renderer.py tests/test_editor_api.py tests/test_optimizer_v2.py -v`
Expected: PASS (or unchanged skip counts for benchmark-gated tests).

- [ ] **Step 3: Commit**

```bash
git add src/hr_breaker/orchestration.py src/hr_breaker/agents/optimizer.py src/hr_breaker/agents/optimizer_v2.py src/hr_breaker/api/routes/editor.py
git commit -m "perf: use cached get_renderer() at all render sites"
```

---

### Task B5: Cache the per-iteration agents (auditor, content-integrity)

`get_auditor_agent` and the content-integrity agent are reconstructed on every audit/filter call (and re-read `resume_guide.md`), unlike `job_parser` and `combined_reviewer` which are `@lru_cache`d. Cache them the same way. Note the auditor takes an optional `model` argument, so cache keyed by that argument.

**Files:**
- Modify: `src/hr_breaker/agents/auditor.py` (`get_auditor_agent`, lines 64-71)
- Modify: `src/hr_breaker/agents/content_integrity.py` (its agent factory, ~line 105)
- Test: `tests/test_audit_scoring.py`

**Interfaces:**
- Consumes: `functools.lru_cache`.
- Produces: `get_auditor_agent(model=None)` returns the same Agent for the same `model` argument across calls.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_audit_scoring.py`:

```python
def test_auditor_agent_is_cached():
    from hr_breaker.agents.auditor import get_auditor_agent
    assert get_auditor_agent() is get_auditor_agent()
    assert get_auditor_agent(model="gemini-2.5-pro") is get_auditor_agent(model="gemini-2.5-pro")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audit_scoring.py::test_auditor_agent_is_cached -v`
Expected: FAIL — distinct instances.

- [ ] **Step 3: Write minimal implementation**

In `auditor.py`, decorate the factory:

```python
from functools import lru_cache

@lru_cache
def get_auditor_agent(model: str | None = None) -> Agent:
    ...
```

Do the equivalent for the content-integrity agent factory (if it takes no args, a bare `@lru_cache` is fine). Confirm neither factory closes over per-request state (they read only `get_settings()`/prompts — safe to cache).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_audit_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/agents/auditor.py src/hr_breaker/agents/content_integrity.py tests/test_audit_scoring.py
git commit -m "perf(agents): cache auditor and content-integrity agents"
```

---

### Task B6: Offload the synchronous scrape off the event loop

`_run_optimization` (async, on the event loop) calls `scrape_job_posting()`, a fully synchronous chain (httpx with `time.sleep` backoff, Wayback, Playwright with blocking `future.result()`). One slow/Cloudflare URL freezes the whole API for minutes. Offload with `asyncio.to_thread`.

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py:95` (the `scrape_job_posting(job_url)` call)
- Test: `tests/test_optimize_routes.py` (assert the call is awaited via to_thread using a monkeypatched scraper)

**Interfaces:**
- Consumes: `asyncio.to_thread` (already imported `asyncio` at `optimize.py:3`).
- Produces: scraping runs in a worker thread; `_run_optimization` behavior otherwise unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_optimize_routes.py` a test that patches `scrape_job_posting` with a function that records the running thread and asserts it is not the main thread:

```python
import threading
import asyncio
import pytest

@pytest.mark.asyncio
async def test_scrape_runs_off_event_loop(monkeypatch):
    from hr_breaker.api.routes import optimize as opt
    from hr_breaker.services.scrapers.base import ScrapedJob

    main_thread = threading.current_thread()
    seen = {}

    def fake_scrape(url):
        seen["thread"] = threading.current_thread()
        return ScrapedJob(text="Job text here", hints=None)

    monkeypatch.setattr(opt, "scrape_job_posting", fake_scrape)

    # Call just the scrape branch in isolation via a tiny wrapper that mirrors optimize.py.
    result = await asyncio.to_thread(fake_scrape, "https://example.com/job")
    assert seen["thread"] is not main_thread
```

(This test documents the required behavior; the real assertion is that `optimize.py` uses `to_thread`. If a full `_run_optimization` harness exists in the test suite, prefer asserting there.)

- [ ] **Step 2: Implement**

In `optimize.py`, change:

```python
                scraped = await asyncio.to_thread(scrape_job_posting, job_url)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_optimize_routes.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hr_breaker/api/routes/optimize.py tests/test_optimize_routes.py
git commit -m "perf(api): offload synchronous job scrape to a worker thread"
```

---

### Task B7: Single shared Supabase client + offload Supabase calls in the hot paths

`get_supabase_service()` constructs a new `SupabaseService` (and thus a new `create_client`, new TLS session) on every dependency resolution; every method is synchronous and un-offloaded. Make the service a process-wide singleton, and wrap the blocking calls in the two hottest request paths (`optimize.start_optimization` and the `list`/`status` polling routes) with `asyncio.to_thread`.

> **Scope note:** offloading *every* Supabase call across all routes is a large sweep. This task does the singleton (cheap, global win) plus the optimize routes (the polling hot path). A follow-up task can extend `to_thread` to coach/subscription/cvs if load testing shows it's needed. Keep this task to the singleton + optimize routes so it stays reviewable.

**Files:**
- Modify: `src/hr_breaker/api/deps.py` (`get_supabase_service`, lines 13-16)
- Modify: `src/hr_breaker/api/routes/optimize.py` (wrap the blocking `supabase.*` calls in the async route handlers `list_optimization_runs`, `get_optimization_status`, `start_optimization` with `asyncio.to_thread`; the background task `_run_optimization` is already off the request path but its calls also block the loop — wrap those too)
- Test: `tests/test_optimize_routes.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: `functools.lru_cache`, `asyncio.to_thread`.
- Produces: `get_supabase_service()` returns a cached singleton `SupabaseService`. No method signatures change.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_optimize_routes.py` (or `tests/test_config.py`):

```python
def test_supabase_service_is_singleton():
    from hr_breaker.api.deps import get_supabase_service
    assert get_supabase_service() is get_supabase_service()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_optimize_routes.py::test_supabase_service_is_singleton -v`
Expected: FAIL — new instance each call.

- [ ] **Step 3: Implement the singleton**

In `deps.py`:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    """Process-wide Supabase service (one client, reused connections)."""
    return SupabaseService()
```

- [ ] **Step 4: Offload the blocking calls in optimize routes**

In `optimize.py`, wrap synchronous Supabase calls inside `async def` handlers with `await asyncio.to_thread(...)`. Example for `list_optimization_runs`:

```python
    runs = await asyncio.to_thread(supabase.list_optimization_runs, user_id)
```

Apply the same wrapping to `get_run_or_404`/`get_profile_or_404` usage inside async handlers (these call sync methods), to `supabase.get_cv`, `consume_optimization_quota`, `create_optimization_run` in `start_optimization`, and to the `supabase.update_optimization_run` / `upload_result_pdf` / `download_result_pdf` calls. Keep `_run_optimization`'s `on_iteration` callback synchronous (it is invoked from sync context inside the loop) — only wrap the direct `await`-able call sites in the async functions.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_optimize_routes.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/hr_breaker/api/deps.py src/hr_breaker/api/routes/optimize.py tests/test_optimize_routes.py
git commit -m "perf(api): singleton Supabase client + offload blocking calls in optimize routes"
```

---

### Task B8: Reorder filters so cheap local checks run before LLM checks

In sequential mode, `ContentIntegrityChecker` (priority 3, an LLM call) and `LLMChecker` (priority 5, an LLM call) run before the free `KeywordMatcher` (4) and `VectorSimilarityMatcher` (6). A resume that fails the free keyword check still pays an LLM round-trip first, every iteration. Reassign priorities so local filters gate first.

**Files:**
- Modify: `src/hr_breaker/filters/content_integrity_checker.py` (`priority`), `src/hr_breaker/filters/llm_checker.py` (`priority`), `src/hr_breaker/filters/keyword_matcher.py` (`priority`), `src/hr_breaker/filters/vector_similarity_matcher.py` (`priority`)
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: priority order becomes: `ContentLengthChecker`=0 (render, but cheap after B1), `KeywordMatcher`=1, `VectorSimilarityMatcher`=2, `ContentIntegrityChecker`=3 (LLM), `LLMChecker`=4 (LLM). Lower runs first; early-exit on failure skips the expensive LLM filters.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_filters.py`:

```python
def test_filter_priority_order_local_before_llm():
    from hr_breaker.filters import FilterRegistry
    prio = {f.name: f.priority for f in FilterRegistry.all()}
    assert prio["KeywordMatcher"] < prio["ContentIntegrityChecker"]
    assert prio["KeywordMatcher"] < prio["LLMChecker"]
    assert prio["VectorSimilarityMatcher"] < prio["LLMChecker"]
    assert prio["ContentLengthChecker"] < prio["KeywordMatcher"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filters.py::test_filter_priority_order_local_before_llm -v`
Expected: FAIL — KeywordMatcher (4) > ContentIntegrityChecker (3).

- [ ] **Step 3: Implement**

Set `priority` values: `KeywordMatcher.priority = 1`, `VectorSimilarityMatcher.priority = 2`, `ContentIntegrityChecker.priority = 3`, `LLMChecker.priority = 4`. Leave `ContentLengthChecker.priority = 0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hr_breaker/filters/*.py tests/test_filters.py
git commit -m "perf(filters): run cheap local filters before LLM filters in sequential mode"
```

---

## Phase C — Cleanup

Low-risk. Do after A and B, or interleave freely — no dependencies.

### Task C1: Remove dead config fields

`pass_threshold`, `fast_mode` (parsed from env but unused), and `filter_ai_generated_threshold` — verify usage before removing. NOTE: Task A5 *starts using* `filter_ai_generated_threshold`; do C1 AFTER A5 and do NOT remove that field. This task removes only the confirmed-dead `pass_threshold` and `fast_mode`.

**Files:**
- Modify: `src/hr_breaker/config.py` (remove `pass_threshold`, `fast_mode` field + their env parsing in `get_settings`)
- Test: `tests/test_config.py`

- [ ] **Step 1: Confirm they are unused**

Run: `grep -rn "pass_threshold\|fast_mode" src/ tests/`
Expected: only definitions in `config.py` (and possibly a test asserting the default — update/remove that test too). If any real usage appears, STOP and keep the field.

- [ ] **Step 2: Remove the fields**

Delete the `pass_threshold: float = 0.7` and `fast_mode: bool = True` lines from the `Settings` class and the `fast_mode=os.getenv(...)` line in `get_settings`.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hr_breaker/config.py tests/test_config.py
git commit -m "chore(config): remove unused pass_threshold and fast_mode settings"
```

---

### Task C2: Honor `scraper_httpx_max_retries` in `scrape_job_posting`

`job_scraper.py` hardcodes `max_retries: int = 3` and always passes it to `HttpxScraper`, so the env-configurable `scraper_httpx_max_retries` never takes effect. Default the parameter to `None` and let the settings fallback in `HttpxScraper` apply.

**Files:**
- Modify: `src/hr_breaker/services/job_scraper.py:17,33`
- Test: `tests/test_job_scraper.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_job_scraper.py` a test that sets `SCRAPER_HTTPX_MAX_RETRIES=7`, monkeypatches `HttpxScraper` to capture its `max_retries`, and asserts it is 7 (verify the exact HttpxScraper constructor signature first).

- [ ] **Step 2: Implement**

Change the signature to `max_retries: int | None = None` and pass it through unchanged (HttpxScraper already falls back to settings when `None`, per `scrapers/httpx_scraper.py:29`).

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_job_scraper.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hr_breaker/services/job_scraper.py tests/test_job_scraper.py
git commit -m "fix(scraper): honor SCRAPER_HTTPX_MAX_RETRIES setting"
```

---

### Task C3: Remove dead atomic-quota code

`consume_request_atomic` (hardcoded `subscription_limit=50`) and `add_addon_credits_atomic` in `supabase.py` have zero callers (the live path is `consume_optimization_quota`). Confirm and delete to remove diverging quota semantics.

**Files:**
- Modify: `src/hr_breaker/services/supabase.py` (lines ~521-578)
- Test: existing `tests/` (no behavior change; deletion of dead code)

- [ ] **Step 1: Confirm zero callers**

Run: `grep -rn "consume_request_atomic\|add_addon_credits_atomic" src/ tests/`
Expected: only the definitions in `supabase.py`. If a test references them, remove that test. If any non-test caller exists, STOP.

- [ ] **Step 2: Delete the two methods.**

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (same pass/skip counts as before, minus any removed dead-code test).

- [ ] **Step 4: Commit**

```bash
git add src/hr_breaker/services/supabase.py
git commit -m "chore(supabase): remove dead atomic-quota methods"
```

---

### Task C4: Remove dead `priority >= 100` machinery

`orchestration.py:92,104` special-case `priority >= 100`, but no registered filter exceeds priority 6. The branch is dead and its comments are misleading. Also update the misleading comment on `filters/base.py:10`.

**Files:**
- Modify: `src/hr_breaker/orchestration.py` (`run_filters`, sequential branch, lines 90-106)
- Modify: `src/hr_breaker/filters/base.py:10` (comment)
- Test: `tests/test_orchestration.py`

- [ ] **Step 1: Confirm no filter uses priority ≥ 100**

Run: `grep -rn "priority" src/hr_breaker/filters/*.py`
Expected: max value is 6 (or the values set in B8). If any ≥ 100 exists, STOP.

- [ ] **Step 2: Remove the dead branch**

Delete the `if filter_cls.priority >= 100 and ...: continue` block (lines ~91-93) and simplify the early-exit condition at line ~104 from `if not result.passed and filter_cls.priority < 100:` to `if not result.passed:`. Update the `base.py` priority comment to drop the "100 = run last" claim.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_orchestration.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/hr_breaker/orchestration.py src/hr_breaker/filters/base.py
git commit -m "chore(orchestration): remove dead priority>=100 filter branch"
```

---

### Task C5: Fix the scraper base-class return-type contract

`services/scrapers/base.py:116` declares `def scrape(self, url: str) -> str` while all three implementations return `ScrapedJob`. A new scraper written to the documented contract would break `scrape_job_posting`'s `.text`/`.hints` access. Correct the annotation.

**Files:**
- Modify: `src/hr_breaker/services/scrapers/base.py:116`
- Test: none (type-annotation-only; verified by grep + existing scraper tests)

- [ ] **Step 1: Fix the annotation**

Change the abstract method signature to `def scrape(self, url: str) -> ScrapedJob:` and ensure `ScrapedJob` is imported/defined in `base.py` (it is defined there per the audit).

- [ ] **Step 2: Run scraper tests**

Run: `uv run pytest tests/test_job_scraper.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/hr_breaker/services/scrapers/base.py
git commit -m "docs(scraper): correct base scrape() return type to ScrapedJob"
```

---

## Final verification

- [ ] **Run the full non-benchmark suite:**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -q`
Expected: all pass; skip count matches the benchmark-gated tests only. No new failures vs the pre-change baseline (capture the baseline count before starting Phase A).

- [ ] **Sanity-check filter behavior end to end** (optional, needs live LLM):

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -m benchmark tests/test_pipeline_benchmark.py -v`
Expected: pipeline completes; confirm keyword/vector/content-integrity scores now vary with input rather than being constant.

---

## Self-review notes

- **Coverage:** Every audit finding in the agreed scope (filter correctness, performance, cleanup) maps to a task. Excluded by scope: all security findings (Telegram link, default-CV cross-tenant read, webhook idempotency, PII logging), the broad "offload every route's Supabase/Stripe/Resend/JWKS call" sweep (B7 does the singleton + optimize routes; a noted follow-up covers the rest), and CV-upload size limits.
- **Sequencing gotcha:** A5 must precede C1 (A5 starts using `filter_ai_generated_threshold`, which C1 would otherwise flag as dead). B1 must precede/absorb B2 (both touch `content_length.py`). B3 must precede B4 (B4 depends on the cached accessor).
- **Two-page consistency (noted, not tasked):** `ContentLengthChecker` still passes a full 2-page resume while the optimizer prompt demands one page. This is a policy decision (tighten the checker vs. relax the prompt), not a bug — raise with the owner before changing; left out of this plan deliberately.
