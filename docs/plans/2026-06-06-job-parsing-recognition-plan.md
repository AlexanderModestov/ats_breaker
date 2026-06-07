# Job Parsing Recognition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve recognition of company name, location, and job title for URL-sourced postings by harvesting schema.org `JobPosting` JSON-LD (plus OpenGraph/`<title>` fallback) deterministically and using it as an authoritative source over the LLM.

**Architecture:** Scrapers gain an `extract_hints(html) -> JobHints` step and return a `ScrapedJob(text, hints)` instead of a bare string. `parse_job_posting` accepts optional `hints` and applies an authoritative-fallback precedence ladder (hint → URL → grounded LLM → review flag) to `company`, `title`, and `location`. `hints=None` reproduces today's exact behavior, so pasted-text / file / orchestration-fallback paths are unaffected.

**Tech Stack:** Python 3.10+, BeautifulSoup4, Pydantic v2, pytest, uv. Design doc: `docs/plans/2026-06-06-job-parsing-recognition-design.md`.

**Conventions:**
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- Test runner: `uv run pytest`.
- Commit after every task. Each changed line should trace to this plan.

---

## Task 1: `JobHints` model

**Files:**
- Modify: `src/hr_breaker/models/job_posting.py`
- Modify: `src/hr_breaker/models/__init__.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
def test_job_hints_defaults_all_none():
    from hr_breaker.models import JobHints
    hints = JobHints()
    assert hints.title is None
    assert hints.company is None
    assert hints.location is None
    assert hints.company_source is None
    assert hints.title_source is None


def test_job_hints_holds_values():
    from hr_breaker.models import JobHints
    hints = JobHints(
        title="Backend Eng", company="Acme", location="Berlin, DE",
        company_source="json-ld", title_source="json-ld",
    )
    assert hints.company == "Acme"
    assert hints.location == "Berlin, DE"
    assert hints.company_source == "json-ld"
    assert hints.title_source == "json-ld"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::test_job_hints_defaults_all_none tests/test_models.py::test_job_hints_holds_values -v`
Expected: FAIL with `ImportError: cannot import name 'JobHints'`

**Step 3: Add the model**

In `src/hr_breaker/models/job_posting.py`, append after the `JobPosting` class:

```python
class JobHints(BaseModel):
    """Structured fields harvested deterministically from page markup.

    Populated by scrapers from schema.org JobPosting JSON-LD or OpenGraph
    meta tags. Each field is None when not found — never invented.
    """

    title: str | None = None
    company: str | None = None
    location: str | None = None
    company_source: str | None = None  # "json-ld" | "meta" — company precedence vs URL slug
    title_source: str | None = None    # "json-ld" | "meta" — json-ld title authoritative; meta is fallback
```

**Step 4: Export it**

In `src/hr_breaker/models/__init__.py`:
- Change `from .job_posting import JobPosting` to `from .job_posting import JobPosting, JobHints`
- Add `"JobHints",` to the `__all__` list (keep alphabetical: after `"IterationContext",`).

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::test_job_hints_defaults_all_none tests/test_models.py::test_job_hints_holds_values -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/hr_breaker/models/job_posting.py src/hr_breaker/models/__init__.py tests/test_models.py
git commit -m "feat: add JobHints model for structured scrape hints"
```

---

## Task 2: `extract_hints` + helpers in base scraper

This is the core of layers A (JSON-LD) and B (og/header). No scraper wiring yet — just the extraction logic and its tests against the base class.

**Files:**
- Modify: `src/hr_breaker/services/scrapers/base.py`
- Test: `tests/test_job_scraper.py`

**Step 1: Write the failing tests**

Add to `tests/test_job_scraper.py` (top of file, extend imports):

```python
from hr_breaker.services.scrapers.base import ScrapedJob
from hr_breaker.models import JobHints


class _Scraper(BaseScraper):
    """Concrete BaseScraper for exercising extract_hints/extract_job_text."""
    name = "test"

    def scrape(self, url: str):  # pragma: no cover - not used
        raise NotImplementedError


class TestExtractHints:
    def setup_method(self):
        self.s = _Scraper()

    def test_jsonld_jobposting_basic(self):
        html = '''
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"JobPosting",
         "title":"Senior Backend Engineer",
         "hiringOrganization":{"@type":"Organization","name":"Acme"},
         "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
            "addressLocality":"Berlin","addressCountry":"DE"}}}
        </script></head><body>...</body></html>
        '''
        hints = self.s.extract_hints(html)
        assert hints.title == "Senior Backend Engineer"
        assert hints.company == "Acme"
        assert hints.location == "Berlin, DE"
        assert hints.company_source == "json-ld"
        assert hints.title_source == "json-ld"

    def test_jsonld_string_hiring_org(self):
        html = '''<script type="application/ld+json">
        {"@type":"JobPosting","title":"Eng","hiringOrganization":"Acme Inc"}
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.company == "Acme Inc"

    def test_jsonld_in_graph(self):
        html = '''<script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"WebSite","name":"Board"},
          {"@type":"JobPosting","title":"Data Scientist",
           "hiringOrganization":{"name":"Globex"}}]}
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.title == "Data Scientist"
        assert hints.company == "Globex"

    def test_jsonld_toplevel_list(self):
        html = '''<script type="application/ld+json">
        [{"@type":"BreadcrumbList"},
         {"@type":"JobPosting","title":"PM","hiringOrganization":{"name":"Initech"}}]
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.company == "Initech"

    def test_jsonld_location_list_takes_first(self):
        html = '''<script type="application/ld+json">
        {"@type":"JobPosting","title":"X","jobLocation":[
          {"address":{"addressLocality":"Paris","addressCountry":"FR"}},
          {"address":{"addressLocality":"Lyon"}}]}
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.location == "Paris, FR"

    def test_jsonld_remote_telecommute(self):
        html = '''<script type="application/ld+json">
        {"@type":"JobPosting","title":"X","jobLocationType":"TELECOMMUTE"}
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.location == "Remote"

    def test_jsonld_type_as_list(self):
        html = '''<script type="application/ld+json">
        {"@type":["JobPosting"],"title":"X","hiringOrganization":{"name":"Y"}}
        </script>'''
        hints = self.s.extract_hints(html)
        assert hints.company == "Y"

    def test_malformed_jsonld_ignored(self):
        html = '<script type="application/ld+json">{not valid json}</script>'
        hints = self.s.extract_hints(html)
        assert hints.title is None
        assert hints.company is None

    def test_og_fallback_when_no_jsonld(self):
        html = '''<html><head>
        <meta property="og:site_name" content="Acme Careers">
        <meta property="og:title" content="Backend Engineer">
        </head><body></body></html>'''
        hints = self.s.extract_hints(html)
        assert hints.company == "Acme Careers"
        assert hints.company_source == "meta"
        assert hints.title == "Backend Engineer"
        assert hints.title_source == "meta"

    def test_title_tag_fallback(self):
        html = "<html><head><title>Frontend Dev - Careers</title></head></html>"
        hints = self.s.extract_hints(html)
        assert hints.title == "Frontend Dev - Careers"
        assert hints.title_source == "meta"

    def test_no_structure_returns_all_none(self):
        html = "<html><body><p>Just some text</p></body></html>"
        hints = self.s.extract_hints(html)
        assert hints == JobHints()

    def test_jsonld_wins_over_og(self):
        html = '''<html><head>
        <meta property="og:site_name" content="Job Board">
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"X","hiringOrganization":{"name":"RealCompany"}}
        </script></head></html>'''
        hints = self.s.extract_hints(html)
        assert hints.company == "RealCompany"
        assert hints.company_source == "json-ld"


def test_extract_job_text_keeps_header():
    html = '''<html><body>
    <header>Acme — Berlin office</header>
    <article><h1>Engineer</h1><p>Build things with Python and SQL daily here.</p></article>
    <footer>Copyright</footer>
    </body></html>'''
    text = _Scraper().extract_job_text(html)
    assert "Acme" in text
    assert "Copyright" not in text
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_job_scraper.py::TestExtractHints -v`
Expected: FAIL — `ImportError: cannot import name 'ScrapedJob'` (and `AttributeError: extract_hints`).

**Step 3: Implement in `src/hr_breaker/services/scrapers/base.py`**

Replace the file's imports and add helpers + methods. New top of file:

```python
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bs4 import BeautifulSoup

from hr_breaker.config import get_settings
from hr_breaker.models import JobHints


@dataclass
class ScrapedJob:
    """Result of scraping: cleaned body text plus structured hints (may be empty)."""

    text: str
    hints: JobHints | None = None
```

Add these module-level helpers (after the `ScrapedJob` dataclass, before `BaseScraper`):

```python
def _clean(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _iter_jsonld(data):
    """Yield candidate dict nodes from a parsed JSON-LD payload.

    Flattens top-level lists and @graph containers.
    """
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld(item)
    elif isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_jsonld(item)


def _types_contains(node: dict, wanted: str) -> bool:
    t = node.get("@type")
    if isinstance(t, str):
        return t == wanted
    if isinstance(t, list):
        return wanted in t
    return False


def _org_name(org) -> str | None:
    if isinstance(org, str):
        return _clean(org)
    if isinstance(org, dict):
        return _clean(org.get("name"))
    if isinstance(org, list):
        for item in org:
            name = _org_name(item)
            if name:
                return name
    return None


def _remote_label(job_location_type) -> str | None:
    if isinstance(job_location_type, str) and job_location_type.upper() == "TELECOMMUTE":
        return "Remote"
    return None


def _format_location(job_location) -> str | None:
    """Collapse a schema.org jobLocation into 'City, Region, Country' (best-effort)."""
    if job_location is None:
        return None
    if isinstance(job_location, list):
        for item in job_location:
            loc = _format_location(item)
            if loc:
                return loc
        return None
    if isinstance(job_location, str):
        return _clean(job_location)
    if not isinstance(job_location, dict):
        return None
    address = job_location.get("address", job_location)
    if isinstance(address, str):
        return _clean(address)
    if not isinstance(address, dict):
        return None
    parts = [
        _clean(address.get("addressLocality")),
        _clean(address.get("addressRegion")),
        _clean(address.get("addressCountry")),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) or None
```

In `BaseScraper`, change the `extract_job_text` decompose line — remove `"header"`:

```python
        # Remove non-content chrome (header kept: often holds company/location)
        for element in soup(["script", "style", "nav", "footer"]):
            element.decompose()
```

Then add two methods to `BaseScraper`:

```python
    def extract_hints(self, html: str) -> JobHints:
        """Harvest structured title/company/location from raw HTML.

        Priority: schema.org JobPosting JSON-LD, then OpenGraph/<title> meta.
        Records per-field provenance (company_source / title_source) so the
        parser can rank meta-sourced values below the URL slug / grounded LLM.
        Never invents — None when nothing is found. Must run on the original
        HTML, before extract_job_text strips <script>.
        """
        soup = BeautifulSoup(html, "html.parser")
        title = company = location = None
        company_source = title_source = None

        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            for node in _iter_jsonld(data):
                if not _types_contains(node, "JobPosting"):
                    continue
                if not title:
                    title = _clean(node.get("title"))
                    if title:
                        title_source = "json-ld"
                if not company:
                    company = _org_name(node.get("hiringOrganization"))
                    if company:
                        company_source = "json-ld"
                if not location:
                    location = _format_location(node.get("jobLocation")) or _remote_label(
                        node.get("jobLocationType")
                    )

        if not company:
            og_site = soup.find("meta", property="og:site_name")
            if og_site and og_site.get("content"):
                company = _clean(og_site["content"])
                if company:
                    company_source = "meta"
        if not title:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = _clean(og_title["content"])
            elif soup.title and soup.title.string:
                title = _clean(soup.title.string)
            if title:
                title_source = "meta"

        return JobHints(
            title=title,
            company=company,
            location=location,
            company_source=company_source,
            title_source=title_source,
        )

    def _build_result(self, html: str) -> ScrapedJob:
        """Bundle cleaned text + structured hints from one HTML document."""
        return ScrapedJob(text=self.extract_job_text(html), hints=self.extract_hints(html))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_scraper.py::TestExtractHints tests/test_job_scraper.py::test_extract_job_text_keeps_header -v`
Expected: PASS (all 13)

**Step 5: Commit**

```bash
git add src/hr_breaker/services/scrapers/base.py tests/test_job_scraper.py
git commit -m "feat: extract JobPosting JSON-LD/og hints in base scraper"
```

---

## Task 3: Scrapers return `ScrapedJob`

Wire all three scrapers to return `ScrapedJob` via `_build_result`, propagate through `scrape_job_posting`, and migrate the existing string-based assertions.

**Files:**
- Modify: `src/hr_breaker/services/scrapers/httpx_scraper.py:90` (`_fetch_and_parse` return)
- Modify: `src/hr_breaker/services/scrapers/wayback_scraper.py:40` (`scrape` return)
- Modify: `src/hr_breaker/services/scrapers/playwright_scraper.py:90` (`scrape_async` return)
- Modify: `src/hr_breaker/services/scrapers/__init__.py` (export `ScrapedJob`)
- Modify: `src/hr_breaker/services/__init__.py` (export `ScrapedJob`)
- Modify: `src/hr_breaker/services/job_scraper.py` (return type annotation + docstring only)
- Test: `tests/test_job_scraper.py`

**Step 1: Update the existing assertions to `.text` (these will fail first)**

In `tests/test_job_scraper.py`, change these assertions to read `.text`:

- `TestHttpxScraper.test_extracts_job_content_from_article`: after `result = scraper.scrape(...)`, change the four assertions to use `result.text` (e.g. `assert 'Software Engineer' in result.text`).
- `TestHttpxScraper.test_extracts_job_content_from_job_div`: `result.text` for both assertions.
- `TestScrapeJobPosting.test_returns_content_on_success`: `assert 'Great Job' in result.text`.
- `TestScrapeJobPosting.test_fallback_to_wayback_on_non_cloudflare_error`: `assert 'Archived Job' in result.text`.

(The `pytest.raises` tests need no change.)

Add one propagation test:

```python
def test_scrape_job_posting_returns_hints():
    html = '''<html><head><script type="application/ld+json">
    {"@type":"JobPosting","title":"Engineer","hiringOrganization":{"name":"Acme"}}
    </script></head><body><article>
    <h1>Engineer</h1><p>Plenty of descriptive job content to pass the length gate.</p>
    </article></body></html>'''
    mock_response = Mock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.raise_for_status = Mock()
    with patch('hr_breaker.services.scrapers.httpx_scraper.httpx.Client') as mock_client:
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        result = scrape_job_posting('https://example.com/job')
    assert isinstance(result, ScrapedJob)
    assert result.hints.company == "Acme"
    assert result.hints.title == "Engineer"
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_job_scraper.py -v`
Expected: FAIL — `.text` on a `str`, and `test_scrape_job_posting_returns_hints` fails (still returns str).

**Step 3: Update the scrapers**

`httpx_scraper.py` — in `_fetch_and_parse`, change the final line and return type:

```python
    def _fetch_and_parse(self, url: str, verify_ssl: bool = True) -> ScrapedJob:
```
```python
        return self._build_result(html)
```
Also change `def scrape(self, url: str) -> str:` → `-> ScrapedJob:` and add `from .base import BaseScraper, CloudflareBlockedError, ScrapingError, ScrapedJob`.

`wayback_scraper.py` — change `def scrape(self, url: str) -> str:` → `-> ScrapedJob:`, change `return self.extract_job_text(html)` → `return self._build_result(html)`, and import `ScrapedJob` from `.base`.

`playwright_scraper.py` — change `async def scrape_async(self, url: str) -> str:` → `-> ScrapedJob:`, change `return self.extract_job_text(html)` → `return self._build_result(html)`, change `def scrape(self, url: str) -> str:` → `-> ScrapedJob:`, and import `ScrapedJob` from `.base`.

`scrapers/__init__.py` — add `from .base import BaseScraper, ScrapedJob` and `"ScrapedJob"` to `__all__`.

`services/__init__.py` — add `ScrapedJob` to the import from `.job_scraper`... but it lives in scrapers; instead add `from .scrapers import ScrapedJob` and `"ScrapedJob"` to `__all__`.

`job_scraper.py` — import for annotation and update signature/docstring:
```python
from .scrapers.base import CloudflareBlockedError, ScrapingError, ScrapedJob
```
```python
def scrape_job_posting(
    url: str,
    max_retries: int = 3,
    use_wayback: bool = True,
    use_playwright: bool = True,
) -> ScrapedJob:
```
No body change — it already returns each scraper's result, which is now a `ScrapedJob`.

**Step 4: Run to verify pass**

Run: `uv run pytest tests/test_job_scraper.py -v`
Expected: PASS (all, including the new propagation test)

**Step 5: Commit**

```bash
git add src/hr_breaker/services/ tests/test_job_scraper.py
git commit -m "feat: scrapers return ScrapedJob with hints"
```

---

## Task 4: Parser precedence ladders + location/title review

Add `hints` to `parse_job_posting` and apply authoritative-fallback precedence to all three fields, with grounding + review flags for `title` and `location`.

**Files:**
- Modify: `src/hr_breaker/agents/job_parser.py`
- Test: `tests/test_job_parser.py`

**Step 1: Write the failing tests**

In `tests/test_job_parser.py`, extend the import and add tests:

```python
from hr_breaker.models import JobHints
```

Add inside `TestParseJobPostingMerge`:

```python
    async def test_jsonld_company_beats_url(self):
        # JSON-LD company is authoritative even over a known URL slug
        llm_job = JobPosting(title="Backend Eng", company="Wrong Co")
        text = "Wrong Co is hiring a Backend Eng."  # LLM grounded, but JSON-LD wins
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text,
                url="https://podcastle.bamboohr.com/careers/56",
                hints=JobHints(company="Acme", company_source="json-ld"),
            )
        assert job.company == "Acme"

    async def test_meta_company_ranks_below_url(self):
        # og:site_name often = the job board; URL slug must win over a meta hint
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # LLM ungrounded
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text,
                url="https://podcastle.bamboohr.com/careers/56",
                hints=JobHints(company="BambooHR", company_source="meta"),
            )
        assert job.company == "podcastle"

    async def test_meta_company_used_when_no_url_and_llm_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # LLM ungrounded, no URL slug
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(company="Acme", company_source="meta")
            )
        assert job.company == "Acme"
        assert "company" not in needs_review

    async def test_jsonld_title_overrides_llm(self):
        llm_job = JobPosting(title="Vague Title", company="Acme")
        text = "Acme is hiring."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(title="Senior Backend Engineer", title_source="json-ld")
            )
        assert job.title == "Senior Backend Engineer"
        assert "title" not in needs_review

    async def test_meta_title_only_used_when_llm_ungrounded(self):
        # grounded LLM title beats a meta-sourced hint (avoids "… | Board" junk)
        llm_job = JobPosting(title="Backend Eng", company="Acme")
        text = "Acme is hiring a Backend Eng."  # LLM grounded
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, hints=JobHints(title="Backend Eng - Acme | JobBoard", title_source="meta")
            )
        assert job.title == "Backend Eng"

    async def test_hint_location_used(self):
        llm_job = JobPosting(title="Eng", company="Acme", location="")
        text = "Acme is hiring an Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(location="Berlin, DE")
            )
        assert job.location == "Berlin, DE"
        assert "location" not in needs_review

    async def test_ungrounded_llm_location_kept_conservatively(self):
        # No hint, LLM location not grounded → kept as-is, never blanked or flagged
        llm_job = JobPosting(title="Eng", company="Acme", location="San Francisco")
        text = "Acme is hiring an Eng in SF."  # "San Francisco" not literally present
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(text)
        assert job.location == "San Francisco"
        assert "location" not in needs_review

    async def test_no_hints_reproduces_old_company_behavior(self):
        # hints=None path must match the pre-existing URL-fallback behavior
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56", hints=None
            )
        assert job.company == "podcastle"
```

The existing `test_returns_empty_needs_review_when_all_grounded` needs **no change** — with conservative location handling an empty location is no longer flagged, so the original assertion (`needs_review == []`) still holds.

**Step 2: Run to verify failure**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: FAIL — `parse_job_posting()` got unexpected keyword `hints`; new location/title assertions fail.

**Step 3: Rewrite `parse_job_posting` in `src/hr_breaker/agents/job_parser.py`**

Add to imports at top:

```python
from hr_breaker.models import JobPosting, JobHints
```

Replace the entire `parse_job_posting` function (lines 118–157) with:

```python
async def parse_job_posting(
    text: str, url: str | None = None, hints: JobHints | None = None
) -> tuple[JobPosting, list[str]]:
    """Parse job posting text into structured data.

    Precedence per field (authoritative-fallback):
      company:  JSON-LD hint -> grounded LLM (URL wins on conflict)
                -> URL slug -> meta hint -> "Not Specified" (review)
      title:    JSON-LD hint -> grounded LLM -> meta hint -> ungrounded LLM (review)
      location: hint -> LLM value kept as-is (conservative: never blanked/flagged)

    Returns the JobPosting plus field names recommended for manual review.
    """
    agent = get_job_parser_agent()
    result = await agent.run(f"Parse this job posting:\n\n{text}")
    job = result.output

    hints = hints or JobHints()
    url_company = extract_company_from_url(url) if url else None
    warnings: list[str] = []
    needs_review: list[str] = []

    # --- company ---
    if hints.company and hints.company_source == "json-ld":
        if _normalize(job.company) != _normalize(hints.company):
            warnings.append(
                f"company: using JSON-LD '{hints.company}' over LLM '{job.company}'"
            )
        job.company = hints.company
        logger.info("field=company source=json-ld value=%s", job.company)
    elif _is_grounded(job.company, text, is_company=True):
        if url_company and not _company_matches(job.company, url_company):
            warnings.append(
                f"URL says '{url_company}' but LLM extracted '{job.company}' — trusting URL"
            )
            job.company = url_company
            logger.info("field=company source=url value=%s", job.company)
        else:
            logger.info("field=company source=llm value=%s", job.company)
    else:
        # LLM ungrounded: URL slug, then meta-sourced hint, then give up.
        warnings.append(f"company '{job.company}' not found in posting text")
        if url_company:
            job.company, src = url_company, "url"
        elif hints.company:
            job.company, src = hints.company, "meta"
        else:
            job.company, src = COMPANY_NOT_SPECIFIED, "none"
        logger.info("field=company source=%s value=%s", src, job.company)

    if job.company == COMPANY_NOT_SPECIFIED:
        needs_review.append("company")

    # --- title ---
    if hints.title and hints.title_source == "json-ld":
        job.title = hints.title
        logger.info("field=title source=json-ld value=%s", job.title)
    elif _is_grounded(job.title, text):
        logger.info("field=title source=llm value=%s", job.title)
    elif hints.title:  # meta/<title> fallback, only when LLM title is ungrounded
        job.title = hints.title
        logger.info("field=title source=meta value=%s", job.title)
    else:
        warnings.append(f"title '{job.title}' not found in posting text")
        needs_review.append("title")
        logger.info("field=title source=llm-ungrounded value=%s", job.title)

    # --- location (conservative: hint wins, otherwise keep LLM value untouched) ---
    if hints.location:
        job.location = hints.location
        logger.info("field=location source=json-ld value=%s", job.location)
    elif job.location:
        grounded = _is_grounded(job.location, text)
        logger.info("field=location source=llm grounded=%s value=%s", grounded, job.location)
    else:
        logger.info("field=location source=none value=")

    if warnings:
        logger.warning("Job parser grounding issues: %s", "; ".join(warnings))

    job.raw_text = text
    return job, needs_review
```

**Step 4: Run to verify pass**

Run: `uv run pytest tests/test_job_parser.py -v`
Expected: PASS (existing + new)

**Step 5: Commit**

```bash
git add src/hr_breaker/agents/job_parser.py tests/test_job_parser.py
git commit -m "feat: authoritative-fallback precedence for company/title/location"
```

---

## Task 5: Thread hints through call sites

Connect scraper output to the parser on the two real URL paths.

**Files:**
- Modify: `src/hr_breaker/api/routes/optimize.py` (in `_run_optimization`: `job_text = job_input` at line 90, `scrape_job_posting` at line 94, `parse_job_posting` at line 115)
- Modify: `src/hr_breaker/cli.py` (lines 53, 86, 180–201)
- Test: `tests/test_optimize_routes.py` (regression — must still pass)

**Step 1: Update `optimize.py`**

At the `job_text = job_input` line (90), initialize a hints holder and unpack the scrape result inside the `if job_url:` block (line 94):

```python
        job_text = job_input
        job_hints = None
        if job_url:
            try:
                scrape_start = time.perf_counter()
                scraped = scrape_job_posting(job_url)
                job_text = scraped.text
                job_hints = scraped.hints
                timing["scrape_job"] = time.perf_counter() - scrape_start
                print(f"⏱️  Scrape job: {timing['scrape_job']:.2f}s")
```

(Leave the `except` blocks unchanged.)

At line 87, pass the hints:

```python
        job, needs_review = await parse_job_posting(job_text, url=job_url, hints=job_hints)
```

**Step 2: Update `cli.py`**

Change `_get_job_text` to return a `ScrapedJob` (import it: `from hr_breaker.services.scrapers.base import ScrapedJob` near the other service imports):

```python
def _get_job_text(job_input: str) -> ScrapedJob:
    """Get job text (+ hints) from URL, file path, or raw text."""
    path = Path(job_input)
    if path.exists():
        return ScrapedJob(text=path.read_text(), hints=None)

    if job_input.startswith(("http://", "https://")):
        try:
            return scrape_job_posting(job_input)
        except CloudflareBlockedError:
            click.echo(f"Site has bot protection. Opening in browser...")
            click.launch(job_input)
            click.echo("Please copy the job description and paste below.")
            click.echo("(Press Enter twice when done)")
            return ScrapedJob(text=_read_multiline_input(), hints=None)
        except ScrapingError as e:
            raise click.ClickException(str(e))

    return ScrapedJob(text=job_input, hints=None)
```

At line 53, capture the result:

```python
    scraped = _get_job_text(job_input)
```

At line 86, derive the URL and pass text + hints:

```python
        job_url = job_input if job_input.startswith(("http://", "https://")) else None
        job, _ = await parse_job_posting(scraped.text, url=job_url, hints=scraped.hints)
```

> If any other code between lines 53 and 86 referenced the old `job_text` variable, update those references to `scraped.text`. (Per current code, `job_text` is used only at 53 and 86.)

**Step 3: Run the route + cli regression tests**

Run: `uv run pytest tests/test_optimize_routes.py -v`
Expected: PASS. If a test mocks `scrape_job_posting` to return a plain string, update that mock to return `ScrapedJob(text="...", hints=None)` — search the test file for `scrape_job_posting` first.

**Step 4: Run the full suite**

Run: `uv run pytest -v`
Expected: all PASS (or only pre-existing unrelated failures, unchanged from before this plan).

**Step 5: Commit**

```bash
git add src/hr_breaker/api/routes/optimize.py src/hr_breaker/cli.py tests/test_optimize_routes.py
git commit -m "feat: thread scrape hints into job parser on URL paths"
```

---

## Done — end-to-end verification

1. Start the API: `uv run uvicorn hr_breaker.api.main:app --reload`
2. Submit an optimization with a Greenhouse/Lever/Ashby URL via the frontend.
3. In the API logs, confirm `field=company source=json-ld value=...`, `field=title source=json-ld ...`, `field=location source=json-ld ...` lines appear — proving structured data is now used.
4. Compare against a known posting: the company/title/location in the result should match the page exactly.
5. Paste raw text (no URL) and confirm behavior is unchanged (`source=llm`, `hints=None`).

## Notes / tradeoffs (decided)

- **Company precedence is source-aware:** only JSON-LD `hiringOrganization` is authoritative over the URL slug. A meta (`og:site_name`) company ranks *below* the URL slug — on job boards `og:site_name` is often the board itself, so this avoids overriding the reliable ATS-slug. `JobHints.company_source` carries this signal.
- **Title:** JSON-LD title is authoritative over the LLM; a meta/`<title>` title is used only when the LLM title is ungrounded (prevents `"… | JobBoard"` suffixes from clobbering a good LLM title). `JobHints.title_source` carries this signal.
- **Location is conservative:** a JSON-LD hint wins; otherwise the LLM location is kept untouched (grounding is logged, not enforced). Location is **never** blanked and **never** added to `needs_review` — the UI cannot edit location, so a review flag would be inert, and blanking risked dropping correct-but-paraphrased values (e.g. LLM "San Francisco" vs text "SF").
- `extract_hints` parses all `<script type="application/ld+json">` blocks; the first `JobPosting` found wins per field (later blocks only fill still-empty fields).
- Removing `<header>` from the decompose list changes the body text fed to the LLM for **all** scraped postings (v1 included) — usually helpful (company/location live there), occasionally adds chrome noise.
- No model/prompt changes; `requirements`/`responsibilities`/`keywords`/`description` remain LLM-produced.
