# Job Parsing Recognition — Design

**Goal:** Improve recognition of **company name, company location, and job title** for postings supplied as URLs. These fields are currently extracted poorly because the richest sources of structured data are discarded before the LLM ever sees them.

**Scope chosen:** A (JSON-LD as primary source) + B (keep header / use meta as fallback) + a slice of C (grounding + fallback + review flag for `location` and `title`, matching what `company` already has).

**Trust model:** Authoritative-fallback. When structured data (JSON-LD / meta) yields `title` / `company` / `location`, it wins deterministically (after a grounding check). The LLM still does the messy work — `requirements`, `responsibilities`, `keywords`, `description` — and serves as the fallback where no structured data exists.

---

## Root cause

All three scrapers (`httpx`, `wayback`, `playwright`) inherit a single `BaseScraper.extract_job_text`, which:

- `decompose()`s `<script>`, `<header>`, `<nav>`, `<footer>` — so the company name and location that usually live in the header, **and** the schema.org `JobPosting` JSON-LD that lives in `<script type="application/ld+json">`, are thrown away before any extraction.
- Returns plain body text only.

So regardless of which scraper wins the fallback chain, the most reliable signal (JSON-LD `JobPosting`) never reaches the parser. Almost every job board / ATS embeds it:

```json
{
  "@type": "JobPosting",
  "title": "Senior Backend Engineer",
  "hiringOrganization": { "name": "Acme", "sameAs": "https://acme.com" },
  "jobLocation": { "address": { "addressLocality": "Berlin", "addressCountry": "DE" } }
}
```

---

## Section 1 — Data structures and flow

Scrapers currently return `str`. To thread structured fields deterministically to the parser, introduce two small structures:

```python
# models/job_posting.py
class JobHints(BaseModel):
    """Structured fields harvested deterministically from the page (JSON-LD/meta/header)."""
    title: str | None = None
    company: str | None = None
    location: str | None = None
    source: str | None = None   # "json-ld" | "meta" | "header" — for logs/diagnostics

# services/scrapers/base.py
@dataclass
class ScrapedJob:
    text: str
    hints: JobHints | None = None
```

**Data flow:**

```
scrape_job_posting(url) ──► ScrapedJob(text, hints)
        │
        ├─ text  ──────────────► LLM parse (requirements, keywords, description, …)
        └─ hints ──────────────► authoritative override for title/company/location
                                  (grounding-checked; empty → URL → LLM)
```

**Signatures touched:**

- `BaseScraper.scrape() -> ScrapedJob` (was `str`). All three scrapers reuse a shared `extract_job_text` + new `extract_hints`.
- `scrape_job_posting(url) -> ScrapedJob`.
- `parse_job_posting(text, url=None, hints=None)` — `hints` optional, default `None` → full backward compatibility for CLI / pasted text / file input / the orchestration fallback branch.
- Call sites: `optimize.py` (main path, has URL) and `cli.py` thread `hints` through.

**Key property:** `hints=None` preserves today's exact behavior everywhere HTML is absent (pasted text, files). No LLM logic changes where structured data does not exist.

---

## Section 2 — Extracting hints (layers A + B)

New method `BaseScraper.extract_hints(html) -> JobHints`, called in `_fetch_and_parse` alongside `extract_job_text`. **Critical:** parse the raw HTML *before* any `decompose()`, otherwise `<script>` / `<header>` are already gone. Three sources, by priority:

**A. JSON-LD `JobPosting` (primary):**

```python
for tag in soup.find_all("script", type="application/ld+json"):
    data = json.loads(tag.string)          # wrapped in try/except — skip malformed JSON
    for node in _iter_jsonld(data):        # data may be a list or carry @graph
        if _types_contains(node, "JobPosting"):
            title    = node.get("title")
            company  = _org_name(node.get("hiringOrganization"))
            location = _format_location(node.get("jobLocation"))
            ...
```

- `jobLocation` may be an object, a list, or contain `address` (a string, or a `PostalAddress` with `addressLocality` / `addressRegion` / `addressCountry`). Helper `_format_location` collapses it to `"City, Country"`. For remote, check `jobLocationType == "TELECOMMUTE"` → `"Remote"`.
- `hiringOrganization` may be a string or an object — handle both (`_org_name`).
- `@graph` and top-level lists are flattened by `_iter_jsonld`.

**B. Fallback, per-field, only when JSON-LD did not yield it:**

- `company` ← `<meta property="og:site_name">`.
- `title` ← `<meta property="og:title">` → `<title>`.
- `location` ← left empty (meta carries no reliable location; resolved in the parser).
- **Stop discarding `<header>`** in `extract_job_text` (decompose only `nav` / `footer` / `script` / `style`) so the body text fed to the LLM also contains the header company/location.

Each populated field sets `hints.source` for log visibility.

**Principle:** `extract_hints` never invents — only what is explicitly present in the markup. Empty → `None`, parser decides next.

---

## Section 3 — Parser precedence, grounding, review flags (slice of C)

`parse_job_posting(text, url=None, hints=None)`. After the LLM run, each of the three fields follows a single precedence ladder:

**company** (extends current logic):

```
1. hints.company (JSON-LD/meta)         ← authoritative, if present
2. URL slug (extract_company_from_url)  ← as today
3. LLM company, if grounded in text
4. "Not Specified" + review flag
```

**title** (currently grounding only, no fallback):

```
1. hints.title                          ← authoritative
2. LLM title, if grounded
3. LLM title + review flag (kept, but flagged)
```

**location** (currently nothing):

```
1. hints.location                       ← authoritative
2. LLM location, if grounded
3. "" + review flag
```

`needs_review` may now contain any of `company` / `title` / `location`. Frontend / CLI already render this list for manual review.

**Logging (the cheap diagnostic):** one line per field — `field=title source=json-ld value=...` (or `source=llm` / `source=url`). After deploy, logs reveal which source actually fires on real URLs.

---

## Testing (TDD)

Follow the existing `job_parser` test patterns.

- **`extract_hints`:** JSON-LD with `@graph` / list / string `hiringOrganization`; `jobLocation` object / list / `PostalAddress` / `TELECOMMUTE`; malformed JSON → `None`; og fallback; structure-less page → all `None`.
- **`parse_job_posting`:** hints beat LLM; empty hints → old behavior (URL / grounding); LLM↔hints conflict → take hints (authoritative); location review flag set when empty.
- **Regression:** `hints=None` reproduces exactly current behavior (CLI / files).
- **Fixtures:** 2–3 real HTML samples (Greenhouse/Lever + a corporate career page) in `tests/fixtures/`.

---

## Files

- Modify: `src/hr_breaker/models/job_posting.py` (add `JobHints`)
- Modify: `src/hr_breaker/services/scrapers/base.py` (`ScrapedJob`, `extract_hints`, keep `<header>`)
- Modify: `src/hr_breaker/services/scrapers/httpx_scraper.py`, `wayback_scraper.py`, `playwright_scraper.py` (return `ScrapedJob`)
- Modify: `src/hr_breaker/services/job_scraper.py` (`scrape_job_posting -> ScrapedJob`)
- Modify: `src/hr_breaker/agents/job_parser.py` (`hints` param, precedence ladders, location/title grounding + review)
- Modify: `src/hr_breaker/api/routes/optimize.py`, `src/hr_breaker/cli.py` (thread `hints`)
- Tests: `tests/test_job_parser.py` (or existing parser test module), `tests/fixtures/`

## Out of scope

- Changing the LLM model or job-parser prompt structure.
- New scraper engines or anti-bot handling.
- Frontend changes beyond the already-supported `needs_review` list.
