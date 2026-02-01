from functools import lru_cache

from pydantic_ai import Agent

from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.models import JobPosting

SYSTEM_PROMPT = """You are a job posting parser. Extract structured information from job postings.

Extract:
- title: The job title
- company: Company name
- location: Job location (city, state, country, or "Remote")
- requirements: List of specific requirements (skills, experience, education)
- responsibilities: List of job responsibilities and duties
- keywords: Technical keywords, tools, technologies mentioned
- description: Brief summary of the role

Be thorough in extracting keywords - include all technologies, tools, frameworks, methodologies mentioned.
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


async def parse_job_posting(text: str) -> JobPosting:
    """Parse job posting text into structured data."""
    agent = get_job_parser_agent()
    result = await agent.run(f"Parse this job posting:\n\n{text}")
    job = result.output
    job.raw_text = text
    return job
