import re
import unicodedata
from functools import lru_cache

from pydantic_ai import Agent

from hr_breaker.agents.url_company_extractor import extract_company_from_url
from hr_breaker.config import get_model_settings, get_settings, logger
from hr_breaker.models import JobPosting, JobHints

COMPANY_NOT_SPECIFIED = "Not Specified"

SYSTEM_PROMPT = """You are a job posting parser. Extract structured information from job postings.

Extract:
- title: The exact job title as written in the posting. Use the full title (e.g. "Senior Software Engineer, Backend Infrastructure" not just "Software Engineer"). Do NOT shorten, rephrase, or generalize it.
- company: The company that is hiring for this role (the employer), NOT a recruitment agency, job board, or staffing firm that posted the listing. If the posting says "on behalf of", "client", or "partner company", extract the actual employer. If the actual employer cannot be determined, use the company name that is most prominently associated with the role.
- location: Job location (city, state, country, or "Remote")
- requirements: List of specific requirements (skills, experience, education)
- responsibilities: List of job responsibilities and duties
- keywords: Technical keywords, tools, technologies mentioned
- description: Brief summary of the role

Rules:
- For title and company: extract ONLY what is explicitly stated in the text. Never infer or fabricate names.
- If the company name is truly absent from the posting, set company to "Not Specified".
- Be thorough in extracting keywords - include all technologies, tools, frameworks, methodologies mentioned.
"""


@lru_cache
def get_job_parser_agent() -> Agent:
    settings = get_settings()
    return Agent(
        f"google-vertex:{settings.gemini_flash_model}",
        output_type=JobPosting,
        system_prompt=SYSTEM_PROMPT,
        model_settings=get_model_settings(),
    )


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


def _company_matches(llm_value: str, url_value: str) -> bool:
    """LLM and URL agree if one contains the other after normalization.

    NOTE: bidirectional substring match is looser than the design doc's risk
    section described — e.g. ('Acme Corp', 'acme-rebrand') is treated as
    agreement (LLM canonical kept), not as a conflict. In practice rebrand-style
    mismatches are rare and recruiter-agency mismatches usually produce
    unrelated slugs that fail this check anyway. Tighten to token-set equality
    if a real-world case surfaces.
    """
    llm_norm = _normalize(_strip_corp_suffix(llm_value))
    url_norm = _normalize(url_value)
    if not llm_norm or not url_norm:
        return False
    return url_norm in llm_norm or llm_norm in url_norm


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
