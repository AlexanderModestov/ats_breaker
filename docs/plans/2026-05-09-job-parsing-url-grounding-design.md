# Job Parsing: URL Signal + Softer Grounding — Design

**Date:** 2026-05-09
**Status:** Approved, ready for plan

## Problem

Some job postings come back with `company = "Not Specified"` or wrong/missing `title` after parsing. Two distinct mechanisms cause this:

1. **Strict grounding rejects valid LLM output.** `_is_grounded()` in `job_parser.py` requires the extracted value to appear in the scraped text either as a substring or as all-words-in-text. Cases like `"Podcastle Inc."` vs body containing only `"Podcastle"`, or `"Senior Engineer, Backend"` vs `"Senior Engineer · Backend"`, fail this check.
2. **The URL itself carries the company name** on most ATS platforms (BambooHR subdomain, Greenhouse/Lever path), but nothing in the pipeline reads the URL.

Out of scope (v1): broken scraping for JS-rendered sources like Telegram widgets — that is a scraper problem, not a parser problem.

## Goals

- When the URL is from a known ATS pattern, use it as a strong signal for `company`.
- When the LLM extracts a canonical name (e.g., `"Podcastle Inc."`) and the URL agrees (`"podcastle"`), keep the LLM's canonical form.
- When LLM and URL disagree, trust the URL — the platform's domain is a hard fact; LLM body extraction can be misled by recruiter mentions, parent companies, etc.
- Stop rejecting valid LLM output for cosmetic reasons (corporate suffix, separator differences, unicode form).

## Non-goals

- Telegram/JS-widget scraping fixes.
- LinkedIn/hh.ru/Indeed structured-data extraction.
- A configurable / pluggable ATS registry (premature; ~8 hosts is fine in code).
- Changing how `title` is replaced when grounding fails (current behavior: log warning, keep LLM value — unchanged).

## Architecture

```
src/hr_breaker/agents/
├── job_parser.py              ← signature change + merge logic
└── url_company_extractor.py   ← NEW (~50 lines)

src/hr_breaker/api/routes/
└── optimize.py                ← pass URL into parse_job_posting
```

**New public signature:**
```python
async def parse_job_posting(text: str, url: str | None = None) -> JobPosting
```

`url` is optional; default `None` preserves existing behavior for CLI and tests.

## URL extractor

Two static tables, no config files.

**Tier 1 — leftmost subdomain is the company:**
- `bamboohr.com`
- `workable.com`
- `recruitee.com`
- `teamtailor.com`
- `breezy.hr`
- `myworkdayjobs.com`

**Tier 2 — first path segment under a known host:**
- `boards.greenhouse.io`
- `jobs.lever.co`
- `jobs.ashbyhq.com`
- `apply.workable.com`

**Reserved subdomains** (to filter false matches): `www`, `jobs`, `careers`, `apply`, `boards`, `hire`.

```python
def extract_company_from_url(url: str) -> str | None:
    """Return raw company slug from known ATS URLs, or None."""
```

Tier 2 is checked **before** Tier 1 because `apply.workable.com` would otherwise match Tier 1 incorrectly. Returns the slug as-is (lowercase, no canonicalization) — the LLM provides canonical form when both agree.

Returns `None` for: unknown hosts, missing/empty subdomain, reserved subdomains, malformed URLs.

## Grounding softening

Replaces `_is_grounded()` in `job_parser.py`. Adds two helpers and one parameter.

```python
SEP_RE = re.compile(r"[·—–,;/|]+")     # NOTE: hyphen-minus "-" is intentionally NOT included
WS_RE = re.compile(r"\s+")

CORP_SUFFIX_RE = re.compile(
    r"[\s,.]+"
    r"(?:Inc\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|Corp\.?|Corporation|"
    r"Co\.?|Company|GmbH|AG|S\.A\.?|B\.V\.?|N\.V\.?|"
    r"Pte\.?|Pvt\.?|Group|Holdings|"
    r"ООО|ОАО|АО|ПАО|ЗАО)"
    r"\s*$",
    re.IGNORECASE,
)


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = SEP_RE.sub(" ", s)
    s = WS_RE.sub(" ", s).strip().lower()
    return s


def _strip_corp_suffix(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = CORP_SUFFIX_RE.sub("", s).strip(" ,.")
    return s


def _is_grounded(value: str, text: str, *, is_company: bool = False) -> bool:
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

**Why hyphen-minus stays:** compound names like `Coca-Cola` should remain a single token; the all-words rule splits on whitespace, so the hyphen lives inside one word.

**Why corp suffix stripping is `is_company`-only:** titles rarely end in `Inc.`/`LLC`, but stripping `"Co"` from `"Senior Engineer, Co"` would be wrong if `Co` ever appears in a title. Cheap to gate; safer.

## Merge logic

```python
def _company_matches(llm_value: str, url_value: str) -> bool:
    """LLM and URL agree if one contains the other after normalization."""
    llm_norm = _normalize(_strip_corp_suffix(llm_value))
    url_norm = _normalize(url_value)
    if not llm_norm or not url_norm:
        return False
    return url_norm in llm_norm or llm_norm in url_norm


async def parse_job_posting(text: str, url: str | None = None) -> JobPosting:
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
        # else: agreement or no URL hint → keep LLM canonical form
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

**Conflict-resolution rule (case 3):** When LLM is grounded but URL disagrees, **URL wins**. Rationale: the URL slug is a hard signal from the platform; LLM body extraction can be misled by recruiter agencies, parent companies mentioned in description, or "on behalf of" wording. The `combined_reviewer` job_parser prompt already tries to handle this, but URLs are a more robust ground truth when available.

## Caller change

In `src/hr_breaker/api/routes/optimize.py` (~line 50–82), capture the URL once and pass it through:

```python
job_url = job_input if job_input.startswith(("http://", "https://")) else None
job_text = job_input
if job_url:
    try:
        job_text = scrape_job_posting(job_url)
        ...
# later:
job = await parse_job_posting(job_text, url=job_url)
```

CLI (`src/hr_breaker/cli.py`) — leave unchanged in v1; CLI users can update later if needed. The default `url=None` keeps current CLI behavior identical.

## Outcome on the originally reported cases

| Input URL | LLM company | URL extractor | Final company |
|---|---|---|---|
| `podcastle.bamboohr.com/...` | `"Podcastle"` (grounded) | `"podcastle"` | `"Podcastle"` (LLM canonical, agrees with URL) |
| `podcastle.bamboohr.com/...` | `"Not Specified"` (grounding fails) | `"podcastle"` | `"podcastle"` (URL fallback) |
| `boards.greenhouse.io/acme/...` | `"Acme Inc."` (grounded after suffix strip) | `"acme"` | `"Acme Inc."` (LLM canonical) |
| `t.me/rfoundersjobs/639` | `"Not Specified"` (scraper returns widget shell) | `None` | `"Not Specified"` — known v1 limitation |

## Testing

- `tests/agents/test_url_company_extractor.py` (~12 cases): each Tier 1 host, each Tier 2 host, reserved subdomains, missing host, malformed URL, `apply.workable.com/...` Tier 2 priority over Tier 1.
- `tests/agents/test_job_parser_grounding.py` (~10 cases): suffix variants (`Inc.`, `LLC`, `ООО`, `GmbH`), separator normalization (`·`, em-dash, en-dash, comma), unicode NFC, empty value, `"Not Specified"` short-circuit, hyphenated names like `Coca-Cola`.
- `tests/agents/test_job_parser_merge.py` (~6 cases): LLM-grounded + URL-agrees, LLM-grounded + URL-disagrees, LLM-fails + URL-present, LLM-fails + no URL, no URL passed at all, `url=""`.

Existing tests must pass without modification — `url` is opt-in.

## Risks

- **URL extractor false positives:** A legitimate URL like `careers.bamboohr.com` (BambooHR's own careers) would map to company `"careers"` if not for the reserved-subdomains list. The list mitigates the obvious cases; obscure misses are tolerable since URL-derived value only wins in conflict or LLM-fail cases.
- **Suffix stripping over-eager:** `"Group"` and `"Holdings"` can appear inside legitimate names. The regex anchors to end-of-string, so `"Volkswagen Group"` strips to `"Volkswagen"` — fine for grounding (it's still a true substring of the canonical name) and the LLM's full output is preserved unchanged.
- **Conflict resolution surprises users:** If LLM extracts `"Acme Corp"` from a body posted on `boards.greenhouse.io/acme-rebrand/...`, the URL slug `"acme-rebrand"` will overwrite the LLM. We log a warning so this is debuggable. Acceptable; the alternative (trusting LLM body extraction over the platform's own URL) was rejected in design.
