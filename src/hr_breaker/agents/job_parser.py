import re
import unicodedata
from functools import lru_cache

from pydantic_ai import Agent

from hr_breaker.agents.url_company_extractor import extract_company_from_url
from hr_breaker.config import get_model_settings, get_settings, logger
from hr_breaker.models import JobPosting

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
        f"google-gla:{settings.gemini_flash_model}",
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
    """LLM and URL agree if one contains the other after normalization."""
    llm_norm = _normalize(_strip_corp_suffix(llm_value))
    url_norm = _normalize(url_value)
    if not llm_norm or not url_norm:
        return False
    return url_norm in llm_norm or llm_norm in url_norm


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
