from datetime import date

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.models import FilterResult, OptimizedResume, ResumeSource


class ContentIntegrityResult(BaseModel):
    """Combined hallucination + AI detection result."""

    # Hallucination fields
    no_hallucination_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Score from 0 to 1 where 1.0 = no fabrications, 0.0 = severe fabrications",
    )
    hallucination_concerns: list[str] = Field(
        default_factory=list,
        description="List of potential fabrication concerns",
    )

    # AI detection fields
    ai_probability: float = Field(
        ge=0.0, le=1.0, description="Probability that content is AI-generated (0-1)"
    )
    ai_indicators: list[str] = Field(
        default_factory=list,
        description="Specific indicators of AI generation found",
    )


SYSTEM_PROMPT = """You perform TWO content integrity checks on resumes in a single pass.

=== TASK 1: HALLUCINATION CHECK ===

Compare the ORIGINAL resume with the OPTIMIZED version. Score how faithful the optimized version is.

SCORING GUIDE:
- 1.0: Perfect - all content traceable to original, only rephrasing/restructuring
- 0.95-0.99: Minor acceptable additions (related tech inference, umbrella terms)
- 0.85-0.94: Light assumptions that are reasonable but noticeable
- 0.7-0.84: Questionable additions - somewhat plausible but stretching
- 0.5-0.69: Significant fabrications - claims that may not be true
- 0.0-0.49: Severe fabrications - fake jobs, degrees, major false claims

ACCEPTABLE (score 0.95+):
- Related technology inference: MySQL user -> PostgreSQL, React -> Vue.js
- General/umbrella terms: "NLP" for text work, "SQL" for database users
- Rephrasing metrics: "1% - 10%" -> "1-10%"
- Summary sections synthesizing existing experience
- Reordering, restructuring, emphasizing existing content
- Commented-out content in original included in optimized

SERIOUS FABRICATIONS (score below 0.7):
- Fabricated job titles, companies, or employment dates
- Invented degrees, certifications, or institutions
- Made-up metrics with specific numbers not in original
- Fake achievements, publications, or awards

=== TASK 2: AI-GENERATION CHECK ===

Analyze the OPTIMIZED resume for signs of AI generation.

CRITICAL: Resumes are INTENTIONALLY formulaic. Every resume guide teaches:
- Action Verb + Task + Result pattern
- Consistent bullet structure
- Quantified metrics
This is GOOD resume writing, NOT AI tells.

NEVER FLAG (expected in professional resumes):
- Uniform bullet structure
- Action verbs: led, developed, managed, implemented
- Quantified achievements
- Perfect grammar

FLAG ONLY (actual AI tells):
- FABRICATED/IMPOSSIBLE claims (timeline contradictions)
- INTERNAL CONTRADICTIONS (different titles for same role)
- BUZZWORD SOUP with ZERO specifics
- GENERIC FILLER repeated verbatim
- Technologies that didn't exist during claimed timeframe

SCORING:
- 0.0-0.3 = Normal professional resume
- 0.3-0.5 = Minor issues, possibly over-polished
- 0.5-0.7 = Multiple genuine AI tells
- 0.7-1.0 = Clearly fabricated or AI-generated

=== OUTPUT ===
Return all four fields: no_hallucination_score, hallucination_concerns, ai_probability, ai_indicators
"""


def get_content_integrity_agent() -> Agent:
    settings = get_settings()
    agent = Agent(
        f"google-gla:{settings.gemini_flash_model}",
        output_type=ContentIntegrityResult,
        system_prompt=SYSTEM_PROMPT,
        model_settings=get_model_settings(),
    )

    @agent.system_prompt
    def add_current_date() -> str:
        return f"Today's date: {date.today().strftime('%B %Y')}"

    return agent


async def check_content_integrity(
    optimized: OptimizedResume,
    source: ResumeSource,
) -> tuple[FilterResult, FilterResult]:
    """Check content integrity: hallucination + AI detection in one call.

    Returns tuple of (hallucination_result, ai_generated_result) for compatibility.
    """
    # Get optimized content
    if optimized.pdf_text:
        optimized_content = optimized.pdf_text
    elif optimized.html:
        optimized_content = optimized.html
    elif optimized.data:
        optimized_content = optimized.data.model_dump_json(indent=2)
    else:
        optimized_content = "(no content)"

    prompt = f"""Perform both content integrity checks on this resume.

=== ORIGINAL RESUME (source of truth) ===
{source.content}

=== OPTIMIZED RESUME (check for fabrication and AI patterns) ===
{optimized_content}

=== END ===

1. Score how faithful the optimized version is to the original (hallucination check)
2. Analyze the optimized version for AI-generation patterns
"""

    agent = get_content_integrity_agent()
    result = await agent.run(prompt)
    r = result.output

    # Build hallucination result
    hall_issues = []
    hall_suggestions = []
    if r.hallucination_concerns:
        hall_issues.append(f"Concerns: {', '.join(r.hallucination_concerns)}")
    if r.no_hallucination_score < 0.9:
        hall_suggestions.append(
            f"Score {r.no_hallucination_score:.2f} below 0.9 threshold"
        )

    hallucination_result = FilterResult(
        filter_name="HallucinationChecker",
        passed=r.no_hallucination_score >= 0.9,
        score=r.no_hallucination_score,
        threshold=0.9,
        issues=hall_issues,
        suggestions=hall_suggestions,
    )

    # Build AI detection result
    ai_issues = []
    ai_suggestions = []
    if r.ai_indicators:
        for indicator in r.ai_indicators:
            ai_issues.append(f"AI giveaway: {indicator}")
        ai_suggestions.append(
            "Fix AI tells: vary bullet lengths/structure, add specific details"
        )

    ai_result = FilterResult(
        filter_name="AIGeneratedChecker",
        passed=r.ai_probability < 0.5,
        score=1.0 - r.ai_probability,
        threshold=0.5,
        issues=ai_issues,
        suggestions=ai_suggestions,
    )

    return hallucination_result, ai_result
