# Job Parsing: URL Signal + Softer Grounding — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `parse_job_posting` use the source URL as a strong signal for `company` on known ATS hosts, and stop rejecting valid LLM output for cosmetic reasons (corporate suffix, separator differences, unicode form).

**Architecture:** A new pure-Python URL extractor (no I/O, no LLM) maps known ATS URLs to a company slug via two static tables (subdomain hosts, path-segment hosts). `job_parser._is_grounded` is replaced with a softened version that NFC-normalizes both sides, replaces a small set of separators with space, and strips trailing corporate suffixes from the LLM company value. `parse_job_posting` gains an optional `url` parameter; when present and the URL extractor yields a slug, it overrides the LLM company on conflict and fills in on grounding failure.

**Tech Stack:** Python 3.10+, `urllib.parse`, `re`, `unicodedata`, `pytest` (`uv run pytest`), `pydantic-ai` (existing `Agent` infrastructure — only mocked in tests).

**Reference design:** [`docs/plans/2026-05-09-job-parsing-url-grounding-design.md`](2026-05-09-job-parsing-url-grounding-design.md).

---

## Task 1: URL company extractor module (Tier 1 + Tier 2 + edge cases)

**Files:**
- Create: `src/hr_breaker/agents/url_company_extractor.py`
- Create: `tests/test_url_company_extractor.py`

**Step 1: Write the failing tests**

Write `tests/test_url_company_extractor.py`:

```python
"""Tests for URL-based company extraction."""

import pytest

from hr_breaker.agents.url_company_extractor import extract_company_from_url


@pytest.mark.parametrize(
    "url,expected",
    [
        # Tier 1: subdomain == company
        ("https://podcastle.bamboohr.com/careers/56", "podcastle"),
        ("https://acme.workable.com/jobs/123", "acme"),
        ("https://foo.recruitee.com/o/bar", "foo"),
        ("https://co.teamtailor.com/jobs/9", "co"),
        ("https://startup.breezy.hr/p/abc", "startup"),
        ("https://corp.myworkdayjobs.com/en-US/External", "corp"),
        # Tier 2: first path segment == company
        ("https://boards.greenhouse.io/podcastle/jobs/123", "podcastle"),
        ("https://jobs.lever.co/acme/abcdef", "acme"),
        ("https://jobs.ashbyhq.com/foo/bar-baz", "foo"),
        ("https://apply.workable.com/podcastle/j/ABC", "podcastle"),
        # Tier 2 must beat Tier 1 for hybrid hosts
        ("https://apply.workable.com/some-co/j/X", "some-co"),
        # Reserved subdomains rejected
        ("https://www.bamboohr.com/", None),
        ("https://jobs.bamboohr.com/", None),
        # Bare host (no company subdomain) rejected
        ("https://bamboohr.com/", None),
        # Tier 2 with empty path rejected
        ("https://boards.greenhouse.io/", None),
        # Tier 2 with reserved first segment rejected
        ("https://boards.greenhouse.io/jobs/123", None),
        # Unknown hosts rejected
        ("https://www.linkedin.com/jobs/view/123", None),
        ("https://t.me/rfoundersjobs/639", None),
        ("https://hh.ru/vacancy/123", None),
        # Malformed / empty inputs
        ("", None),
        ("not a url", None),
        ("ftp://podcastle.bamboohr.com/", "podcastle"),  # scheme-agnostic; host is what matters
    ],
)
def test_extract_company_from_url(url, expected):
    assert extract_company_from_url(url) == expected
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_url_company_extractor.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'hr_breaker.agents.url_company_extractor'`.

**Step 3: Write the minimal implementation**

Create `src/hr_breaker/agents/url_company_extractor.py`:

```python
"""Extract company slug from known ATS URLs.

Used by job_parser as a strong signal for company name when the LLM
extraction is ungrounded or disagrees with the URL.
"""

from urllib.parse import urlparse

# Tier 1: leftmost subdomain is the company.
# E.g. podcastle.bamboohr.com -> "podcastle"
SUBDOMAIN_HOSTS = {
    "bamboohr.com",
    "workable.com",
    "recruitee.com",
    "teamtailor.com",
    "breezy.hr",
    "myworkdayjobs.com",
}

# Tier 2: first path segment under a known host.
# E.g. boards.greenhouse.io/podcastle/jobs/123 -> "podcastle"
PATH_HOSTS = {
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "apply.workable.com",
}

# Subdomains/path-segments that are common platform routes, not companies.
RESERVED = {"www", "jobs", "careers", "apply", "boards", "hire"}


def extract_company_from_url(url: str) -> str | None:
    """Return company slug from known ATS URLs, or None.

    Tier 2 (path-host) is checked first because some hosts like
    apply.workable.com would otherwise match Tier 1 with the wrong slug.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None

    # Tier 2: explicit path-host match
    if host in PATH_HOSTS:
        segments = [s for s in parsed.path.split("/") if s]
        if segments and segments[0] not in RESERVED:
            return segments[0]
        return None

    # Tier 1: subdomain match
    for ats_host in SUBDOMAIN_HOSTS:
        if host == ats_host or host.endswith("." + ats_host):
            prefix = host[: -len(ats_host)].rstrip(".")
            if not prefix:
                return None
            first_label = prefix.split(".")[0]
            if first_label in RESERVED:
                return None
            return first_label

    return None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_url_company_extractor.py -v`
Expected: All ~22 cases PASS.

**Step 5: Commit**

```bash
git add src/hr_breaker/agents/url_company_extractor.py tests/test_url_company_extractor.py
git commit -m "feat(job-parser): add URL company extractor for known ATS hosts"
```

---

## Task 2: Grounding helpers — normalize and strip corporate suffix

**Files:**
- Modify: `src/hr_breaker/agents/job_parser.py`
- Create: `tests/test_job_parser.py`

**Step 1: Write the failing tests**

Create `tests/test_job_parser.py`:

```python
"""Tests for job_parser grounding helpers and merge logic."""

import pytest

from hr_breaker.agents.job_parser import (
    COMPANY_NOT_SPECIFIED,
    _normalize,
    _strip_corp_suffix,
    _is_grounded,
)


class TestNormalize:
    def test_lowercases(self):
        assert _normalize("Hello World") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize("a   b\tc\nd") == "a b c d"

    def test_replaces_separators_with_space(self):
        # middle dot, em-dash, en-dash, comma, semicolon, slash, pipe
        assert _normalize("a · b — c – d, e; f/g|h") == "a b c d e f g h"

    def test_keeps_hyphen_minus(self):
        assert _normalize("Coca-Cola") == "coca-cola"

    def test_unicode_nfc(self):
        # decomposed "é" (e + combining acute) → composed "é"
        assert _normalize("Café") == _normalize("Café")


class TestStripCorpSuffix:
    @pytest.mark.parametrize(
        "input_,expected",
        [
            ("Podcastle Inc.", "Podcastle"),
            ("Podcastle Inc", "Podcastle"),
            ("Acme LLC", "Acme"),
            ("Acme L.L.C.", "Acme"),
            ("Foo Ltd.", "Foo"),
            ("Foo Limited", "Foo"),
            ("Bar Corp", "Bar"),
            ("Bar Corporation", "Bar"),
            ("Baz Co.", "Baz"),
            ("Baz Company", "Baz"),
            ("Acme GmbH", "Acme"),
            ("Acme S.A.", "Acme"),
            ("Acme B.V.", "Acme"),
            ("Acme Pte Ltd", "Acme"),
            ("Volkswagen Group", "Volkswagen"),
            ("Hertz Holdings", "Hertz"),
            ("ООО Ромашка", "ООО Ромашка"),  # leading suffix not stripped (anchored to end)
            ("Ромашка ООО", "Ромашка"),
            ("Acme, Inc., LLC", "Acme"),  # cascading
            ("Plain Name", "Plain Name"),  # no-op
            ("", ""),
        ],
    )
    def test_strips_trailing_corp_suffix(self, input_, expected):
        assert _strip_corp_suffix(input_) == expected


class TestIsGrounded:
    def test_empty_value_is_grounded(self):
        assert _is_grounded("", "any text") is True

    def test_unknown_short_circuits(self):
        assert _is_grounded("Unknown", "") is True
        assert _is_grounded(COMPANY_NOT_SPECIFIED, "") is True

    def test_substring_match_passes(self):
        assert _is_grounded("Podcastle", "Working at Podcastle is great") is True

    def test_all_words_match_passes(self):
        assert _is_grounded(
            "Senior Backend Engineer",
            "We seek a Senior Engineer with Backend skills",
        ) is True

    def test_separator_difference_passes_with_normalization(self):
        assert _is_grounded(
            "Senior Engineer, Backend",
            "Senior Engineer · Backend at Acme",
        ) is True

    def test_unrelated_value_fails(self):
        assert _is_grounded("Microsoft", "Working at Apple is great") is False

    def test_company_suffix_stripped_when_is_company(self):
        assert _is_grounded(
            "Podcastle Inc.",
            "We are Podcastle, a great place",
            is_company=True,
        ) is True

    def test_company_suffix_not_stripped_for_title(self):
        # Title with trailing "Co" should not be stripped — but also the words rule
        # would still find "Senior Engineer" in text; this tests the gate, not behavior.
        # Using a clearly-failing case to prove the suffix isn't stripped:
        assert _is_grounded(
            "Solo Inc.",
            "Solo is hiring",
            is_company=False,
        ) is False  # "Inc." not in text, suffix not stripped → fails

    def test_cyrillic_suffix_company(self):
        assert _is_grounded(
            "Ромашка ООО",
            "Работаем в компании Ромашка уже 10 лет",
            is_company=True,
        ) is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: All tests FAIL with `ImportError` for `_normalize`, `_strip_corp_suffix`; existing `_is_grounded` doesn't accept `is_company` keyword.

**Step 3: Replace `_is_grounded` and add helpers in `job_parser.py`**

In `src/hr_breaker/agents/job_parser.py`:

1. Add imports at top:

```python
import re
import unicodedata
```

2. Replace the existing `_is_grounded` function (lines 39–50) with this block:

```python
# Separators replaced with space during normalization.
# NOTE: hyphen-minus "-" is intentionally NOT included (compound words like Coca-Cola).
_SEP_RE = re.compile(r"[·—–,;/|]+")
_WS_RE = re.compile(r"\s+")

# Trailing corporate suffixes — only stripped when checking *company* field.
# Anchored to end-of-string with a leading separator (space/comma/period).
_CORP_SUFFIX_RE = re.compile(
    r"[\s,.]+"
    r"(?:Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|Corp\.?|Corporation|"
    r"Co\.?|Company|GmbH|AG|S\.A\.?|B\.V\.?|N\.V\.?|"
    r"Pte\.?|Pvt\.?|Group|Holdings|"
    r"ООО|ОАО|АО|ПАО|ЗАО)"
    r"\s*$",
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    """NFC + separator-to-space + whitespace collapse + lowercase."""
    s = unicodedata.normalize("NFC", s)
    s = _SEP_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


def _strip_corp_suffix(s: str) -> str:
    """Strip trailing corporate suffixes (Inc., LLC, ООО, ...) repeatedly."""
    prev = None
    while prev != s:
        prev = s
        s = _CORP_SUFFIX_RE.sub("", s).strip(" ,.")
    return s


def _is_grounded(value: str, text: str, *, is_company: bool = False) -> bool:
    """Check if extracted value actually appears in the source text.

    Softens strict substring matching by:
      - NFC-normalizing both sides
      - Collapsing common separators to spaces
      - Stripping trailing corporate suffixes (when is_company=True)
    """
    if not value:
        return True
    if value.strip().lower() in ("unknown", COMPANY_NOT_SPECIFIED.lower()):
        return True

    norm_value = _strip_corp_suffix(value) if is_company else value
    norm_value = _normalize(norm_value)
    norm_text = _normalize(text)

    if not norm_value:
        return True
    if norm_value in norm_text:
        return True
    return all(w in norm_text for w in norm_value.split())
```

3. Update the call site for company in `parse_job_posting` (was line 60):

```python
    if not _is_grounded(job.company, text, is_company=True):
        warnings.append(f"company '{job.company}' not found in posting text")
        job.company = COMPANY_NOT_SPECIFIED
```

(Title call stays as-is for now — Task 4 will revisit.)

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: All tests PASS.

**Step 5: Run full test suite to confirm no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests still pass. (`-x` stops at first failure for fast triage.)

**Step 6: Commit**

```bash
git add src/hr_breaker/agents/job_parser.py tests/test_job_parser.py
git commit -m "feat(job-parser): soften grounding with NFC + separator + corp-suffix normalization"
```

---

## Task 3: Add URL parameter and merge logic to `parse_job_posting`

**Files:**
- Modify: `src/hr_breaker/agents/job_parser.py`
- Modify: `tests/test_job_parser.py`

**Step 1: Add the failing tests for merge logic**

Append to `tests/test_job_parser.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from hr_breaker.agents.job_parser import parse_job_posting
from hr_breaker.models import JobPosting


def _mock_agent_returning(job: JobPosting):
    """Build a mock pydantic-ai Agent whose .run() returns the given JobPosting."""
    fake_result = MagicMock()
    fake_result.output = job
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=fake_result)
    return mock_agent


@pytest.mark.asyncio
class TestParseJobPostingMerge:
    async def test_no_url_keeps_llm_value_when_grounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
        text = "Podcastle is hiring a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(text)
        assert job.company == "Podcastle Inc."

    async def test_no_url_replaces_with_not_specified_when_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Podcastle is hiring a Backend Eng."  # Microsoft not in text
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(text)
        assert job.company == COMPANY_NOT_SPECIFIED

    async def test_url_fills_in_when_llm_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # neither company appears
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "podcastle"

    async def test_url_keeps_llm_canonical_when_agreeing(self):
        llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
        text = "Podcastle is hiring a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "Podcastle Inc."  # LLM canonical wins on agreement

    async def test_url_overrides_on_conflict(self):
        llm_job = JobPosting(title="Backend Eng", company="Acme Corp")
        text = "Acme Corp posted: Backend Eng."  # LLM grounded but URL says podcastle
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "podcastle"

    async def test_url_with_unknown_host_is_noop(self):
        llm_job = JobPosting(title="Backend Eng", company="Acme Corp")
        text = "Acme Corp posted: Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job = await parse_job_posting(text, url="https://t.me/rfoundersjobs/639")
        assert job.company == "Acme Corp"
```

Add `pytest-asyncio` marker config check — verify `pyproject.toml` already has `asyncio_mode = "auto"` or similar:

Run: `uv run pytest tests/test_job_parser.py::TestParseJobPostingMerge -v --collect-only`
If collection complains about missing async support, add to top of test file:

```python
pytestmark = pytest.mark.asyncio
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_job_parser.py::TestParseJobPostingMerge -v`
Expected: FAIL — `parse_job_posting` doesn't accept `url` keyword (TypeError) or fails on assertion when `url` parameter is absent.

**Step 3: Implement the merge logic**

In `src/hr_breaker/agents/job_parser.py`:

1. Add import at top:

```python
from hr_breaker.agents.url_company_extractor import extract_company_from_url
```

2. Add the helper before `parse_job_posting`:

```python
def _company_matches(llm_value: str, url_value: str) -> bool:
    """LLM and URL agree if one contains the other after normalization."""
    llm_norm = _normalize(_strip_corp_suffix(llm_value))
    url_norm = _normalize(url_value)
    if not llm_norm or not url_norm:
        return False
    return url_norm in llm_norm or llm_norm in url_norm
```

3. Replace the body of `parse_job_posting` (currently lines 53–70) with:

```python
async def parse_job_posting(text: str, url: str | None = None) -> JobPosting:
    """Parse job posting text into structured data.

    If `url` is provided and matches a known ATS pattern, the URL-derived
    company slug is used as a strong signal: it fills in when the LLM
    extraction fails grounding, and overrides the LLM on conflict.
    """
    agent = get_job_parser_agent()
    result = await agent.run(f"Parse this job posting:\n\n{text}")
    job = result.output

    url_company = extract_company_from_url(url) if url else None
    warnings: list[str] = []

    if _is_grounded(job.company, text, is_company=True):
        if url_company and not _company_matches(job.company, url_company):
            warnings.append(
                f"URL says '{url_company}' but LLM extracted '{job.company}' — trusting URL"
            )
            job.company = url_company
        # else: LLM agrees with URL (or no URL hint) → keep LLM canonical form
    else:
        warnings.append(f"company '{job.company}' not found in posting text")
        job.company = url_company or COMPANY_NOT_SPECIFIED

    if not _is_grounded(job.title, text):
        warnings.append(f"title '{job.title}' not found in posting text")

    if warnings:
        logger.warning("Job parser grounding issues: %s", "; ".join(warnings))

    job.raw_text = text
    return job
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: All tests in both `TestIsGrounded` and `TestParseJobPostingMerge` PASS.

**Step 5: Run full test suite to confirm no regressions**

Run: `uv run pytest tests/ -x -q`
Expected: All existing tests still pass. The new `url=None` default keeps existing callers' behavior identical.

**Step 6: Commit**

```bash
git add src/hr_breaker/agents/job_parser.py tests/test_job_parser.py
git commit -m "feat(job-parser): use URL as strong signal for company on known ATS hosts"
```

---

## Task 4: Wire URL through the optimize route

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py:55-82`

**Step 1: Inspect current code**

Read `src/hr_breaker/api/routes/optimize.py` lines 50–90. The `_run_optimization` background task currently does:

```python
job_text = job_input
if job_input.startswith("http://") or job_input.startswith("https://"):
    try:
        job_text = scrape_job_posting(job_input)
        ...
# later:
job = await parse_job_posting(job_text)
```

We need to remember the URL after scraping and pass it into `parse_job_posting`.

**Step 2: Edit `optimize.py`**

Replace the URL detection + parsing block. Find this:

```python
        # Check if job_input is a URL or text
        job_text = job_input
        if job_input.startswith("http://") or job_input.startswith("https://"):
            try:
                scrape_start = time.perf_counter()
                job_text = scrape_job_posting(job_input)
                timing["scrape_job"] = time.perf_counter() - scrape_start
                print(f"⏱️  Scrape job: {timing['scrape_job']:.2f}s")
```

Add a `job_url` variable just before, and use it consistently:

```python
        # Check if job_input is a URL or text
        job_url = (
            job_input
            if job_input.startswith(("http://", "https://"))
            else None
        )
        job_text = job_input
        if job_url:
            try:
                scrape_start = time.perf_counter()
                job_text = scrape_job_posting(job_url)
                timing["scrape_job"] = time.perf_counter() - scrape_start
                print(f"⏱️  Scrape job: {timing['scrape_job']:.2f}s")
```

Then find this line further down (currently `~line 81`):

```python
        job = await parse_job_posting(job_text)
```

Replace with:

```python
        job = await parse_job_posting(job_text, url=job_url)
```

**Step 3: Sanity-check by running the app's tests**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass.

**Step 4: Manual verification (optional, recommended)**

Start the API: `./scripts/run-api.sh` (or `uv run uvicorn hr_breaker.api.main:app --reload`).

Trigger an optimization with a BambooHR URL (the original example: `https://podcastle.bamboohr.com/careers/56?source=aWQ9MjE%3D`) via the frontend. Then check the database / logs:

- The optimization run's `job_parsed.company` should now be `"Podcastle"` (LLM canonical) or `"podcastle"` (URL fallback) instead of `"Not Specified"`.
- Console log line `Job parsed: <title> at <company>` should show a real company.

If the page can't be scraped (Cloudflare 403), this manual test won't trigger the parser at all — note this as expected behavior; the URL signal only helps once we have *some* text. Use a paste-the-job-text flow with a manually-set URL only if needed. (Skipping a deeper E2E here is fine — unit tests cover the merge logic.)

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/optimize.py
git commit -m "feat(optimize): pass source URL into parse_job_posting"
```

---

## Done

After Task 4 commits, the feature is complete:
- BambooHR-style and Greenhouse/Lever-style URLs now produce a real `company` value even when the page body is sparse.
- `"Podcastle Inc."` no longer trips the grounding check.
- All existing tests pass; no behavior change for non-URL job_input or for unknown hosts.
- Telegram (`t.me/...`) remains a known v1 limitation, tracked separately.

Final sanity sweep:

```bash
uv run pytest tests/ -q
git log --oneline -5
```

Expected: clean test run + four new commits on `dev`:
```
feat(optimize): pass source URL into parse_job_posting
feat(job-parser): use URL as strong signal for company on known ATS hosts
feat(job-parser): soften grounding with NFC + separator + corp-suffix normalization
feat(job-parser): add URL company extractor for known ATS hosts
```
