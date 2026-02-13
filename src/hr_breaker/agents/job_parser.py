from functools import lru_cache

from pydantic_ai import Agent

from hr_breaker.config import get_model_settings, get_settings, logger
from hr_breaker.models import JobPosting

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
- If the company name is truly absent from the posting, set company to "Unknown".
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


def _is_grounded(value: str, text: str) -> bool:
    """Check if extracted value actually appears in the source text."""
    text_lower = text.lower()
    value_lower = value.lower().strip()
    if not value_lower or value_lower == "unknown":
        return True
    # Exact substring match
    if value_lower in text_lower:
        return True
    # Check if all words from the value appear in the text
    words = value_lower.split()
    return all(w in text_lower for w in words)


async def parse_job_posting(text: str) -> JobPosting:
    """Parse job posting text into structured data."""
    agent = get_job_parser_agent()
    result = await agent.run(f"Parse this job posting:\n\n{text}")
    job = result.output

    warnings = []
    if not _is_grounded(job.company, text):
        warnings.append(f"company '{job.company}' not found in posting text")
        job.company = "Unknown"
    if not _is_grounded(job.title, text):
        warnings.append(f"title '{job.title}' not found in posting text")

    if warnings:
        logger.warning("Job parser grounding issues: %s", "; ".join(warnings))

    job.raw_text = text
    return job
