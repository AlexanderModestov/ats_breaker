import logging
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent, BinaryContent

from hr_breaker.agents.combined_reviewer import pdf_to_image
from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.filters.data_validator import validate_html
from hr_breaker.filters.keyword_matcher import check_keywords
from hr_breaker.models import (
    IterationContext,
    JobPosting,
    OptimizedResume,
    ResumeSource,
)
from hr_breaker.models.audit import AuditScore
from hr_breaker.services.length_estimator import estimate_content_length
from hr_breaker.services.renderer import HTMLRenderer, RenderError
from hr_breaker.utils import extract_text_from_html

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


def _load_resume_guide() -> str:
    guide_path = TEMPLATE_DIR / "resume_guide.md"
    return guide_path.read_text()


OPTIMIZER_V2_PROMPT = r"""
You are a resume optimization expert applying a structured 8-dimension framework.
Extract content from the user's resume and produce an optimized HTML resume for the job posting.

INPUT: The user's resume text (any format).

OUTPUT: Generate HTML for the <body> of a resume PDF. Do NOT include <html>, <head>, or <body> tags.
Also produce a structured audit score rating the optimized resume across all 8 dimensions.

LANGUAGE RULE (CRITICAL):
- Output MUST be in the SAME LANGUAGE as the original resume
- Never translate regardless of job posting language

STRICT RULES — NEVER VIOLATE:
1. NEVER add technologies, platforms, or tools not in original
2. NEVER fabricate jobs, degrees, certifications, achievements, or metrics
3. NEVER invent metrics or numbers not in original
4. NEVER remove skills or keywords present in the original
5. NEVER use em dash, "delve", "leverage", "robust", or other LLM-generated text markers
6. NEVER add <script> tags
7. NEVER translate the resume

CONTENT BUDGET:
- Target: ~500 words, ~4000 characters (rough estimates; page_count is authoritative)
- Do not return until check_content_length confirms fits_one_page=true

8-DIMENSION OPTIMIZATION — apply each dimension in order:

1. ATS COMPATIBILITY
   - Use standard section headers: "Professional Experience", "Education", "Skills"
   - No tables, columns, text boxes, or graphics
   - Contact info in body (not header/footer of the page)
   - Target role keywords present in resume body, not just skills section

2. RECRUITER SCAN (7-second F-pattern)
   - Name and current title clear and prominent
   - Quantified achievements in the most-scanned position (first bullet of each role)
   - Bullets, not paragraphs
   - Gaps or short tenures present but not over-explained

3. BULLET QUALITY — apply XYZ formula to every bullet
   - XYZ: "Accomplished X measured by Y by doing Z"
   - "So What?" test: each bullet must answer "so what?" at least twice
   - Quantify: hard numbers when available, proxy metrics otherwise
     (e.g. "reduced p95 latency from 800ms to 120ms", "cut review cycle from 3 days to same-day")
   - Vary action verbs — no verb used more than twice across the resume
   - Avoid: "responsible for", "helped with", "worked on"

4. SENIORITY CALIBRATION — match verb tier to candidate's evident level
   - IC:       built / implemented / developed / shipped / debugged
   - Manager:  managed / led / coordinated / hired / grew
   - Director: scaled / established / directed / launched / owned
   - VP+:      championed / orchestrated / transformed / set strategy
   - Impact scope must grow across roles (individual → team → org)

5. KEYWORD COVERAGE
   - Target role keywords from job posting present in resume body
   - Skills ordered by relevance to the job (most relevant first)
   - Specific beats generic ("PostgreSQL, Redis" beats "Databases")

6. STRUCTURE AND LAYOUT
   - Single column only
   - Section order: Summary → Experience → Education → Skills
   - Summary: 2-3 lines, hooks the reader, answers "why this candidate for this role?"
   - Length: 1 page (enforced via check_content_length)

7. CONCERN MANAGEMENT
   - If employment gaps exist: neutral framing, no excuses
   - If short tenures exist: one-line rationale in role description
   - If career switch: bridge sentence connecting past domain to target role

8. CONSISTENCY AND POLISH
   - Current role: present tense; past roles: past tense
   - Punctuation: consistent (all bullets end with period, or none do)
   - No first person ("I led" → "Led")
   - No buzzword padding
   - Dates: consistent format throughout

TOOLS:
- check_content_length(html) — REQUIRED before returning; must confirm fits_one_page=true
- check_keywords_tool(html) — use to verify keyword coverage
- preview_resume(html) — use only if you suspect layout problems
- validate_structure(html) — use after major structural changes

AUDIT:
Rate the OPTIMIZED resume (after your changes) across all 8 dimensions.
Be honest — if a dimension is still Weak after optimization, say so.
top_fixes: list the 3 highest-impact remaining improvements in priority order.
If no concerns exist for concern_management, use "NA".

{resume_guide}
"""


HOW_TO_FIX_FILTERS_V2 = """
HOW TO FIX FAILED FILTERS:
- KeywordMatcher failed → call check_keywords_tool(html). For each missing keyword, search the ORIGINAL resume — if present, surface it in Skills/Summary/relevant bullet. Never invent.
- VectorSimilarityMatcher failed → rephrase Summary and bullet leads with job description terminology. Reorder bullets to lead with most JD-relevant.
- LLMChecker failed → read the issues; usually generic phrasing or LLM-tells. Tighten wording to original tone.
- ContentIntegrityChecker failed → restore removed or paraphrased real facts verbatim.
- DataValidator failed → fix HTML structure. Run validate_structure(html).
- ContentLengthChecker failed → use check_content_length to confirm; trim Summary first, then less-relevant bullets.
"""


class OptimizerV2Result(BaseModel):
    """Output from the v2 optimizer agent."""

    html: str
    changes: list[str]
    audit: AuditScore


def get_optimizer_v2_agent(job: JobPosting, source: ResumeSource) -> Agent:
    """Create optimizer v2 agent with 8-dimension prompt."""
    settings = get_settings()
    resume_guide = _load_resume_guide()
    system_prompt = OPTIMIZER_V2_PROMPT.format(resume_guide=resume_guide)
    agent = Agent(
        f"google-vertex:{settings.gemini_pro_model}",
        output_type=OptimizerV2Result,
        system_prompt=system_prompt,
        model_settings=get_model_settings(),
    )

    @agent.system_prompt
    def add_current_date() -> str:
        return f"Today's date: {date.today().strftime('%B %Y')}"

    _length_cache: dict[str, dict] = {}

    @agent.tool_plain
    def check_content_length(html: str) -> dict:
        """Check if HTML content fits one page by rendering PDF."""
        cached = _length_cache.get(html)
        if cached is not None:
            logger.debug("check_content_length cache hit")
            return cached

        est = estimate_content_length(html)
        try:
            renderer = HTMLRenderer()
            render_result = renderer.render(html)
            page_count = render_result.page_count
            fits_one_page = page_count == 1
        except RenderError as e:
            err_result = {
                "fits_one_page": False,
                "error": f"Render failed: {e}",
                "estimates": {
                    "chars": est.chars,
                    "words": est.words,
                    "note": "Estimates only - fix render error first",
                },
            }
            _length_cache[html] = err_result
            return err_result

        result = {
            "fits_one_page": fits_one_page,
            "page_count": page_count,
            "estimates": {
                "chars": est.chars,
                "words": est.words,
                "limits": {"chars": settings.resume_max_chars, "words": settings.resume_max_words},
                "note": "Character/word counts are rough estimates, page_count is authoritative",
            },
        }
        if not fits_one_page:
            result["suggestion"] = f"Content spans {page_count} pages. Remove ~{est.overflow_words} words (estimate)"
        _length_cache[html] = result
        return result

    @agent.tool_plain
    def preview_resume(html: str) -> BinaryContent:
        """Render HTML to PDF and return preview image. Use to visually check layout."""
        logger.debug("preview_resume called")
        renderer = HTMLRenderer()
        result = renderer.render(html)
        image_bytes, _ = pdf_to_image(result.pdf_bytes)
        return BinaryContent(data=image_bytes, media_type="image/png")

    @agent.tool_plain
    def check_keywords_tool(html: str) -> dict:
        """Check keyword coverage vs job posting. Returns missing keywords ranked by TF-IDF importance."""
        resume_text = extract_text_from_html(html)
        result = check_keywords(resume_text, job)
        logger.debug(
            "check_keywords called: score=%.2f, missing=%d",
            result.score,
            len(result.missing_keywords),
        )
        return {
            "passed": result.passed,
            "score": round(result.score, 2),
            "missing_keywords": result.missing_keywords,
        }

    @agent.tool_plain
    def validate_structure(html: str) -> dict:
        """Check HTML structure - headers, sections, no scripts."""
        valid, issues = validate_html(html)
        logger.debug(
            "validate_structure called: valid=%s, issues=%d", valid, len(issues)
        )
        return {"valid": valid, "issues": issues}

    return agent


async def optimize_resume_v2(
    source: ResumeSource,
    job: JobPosting,
    context: IterationContext,
) -> OptimizedResume:
    """Optimize resume using the 8-dimension approach."""
    prompt = f"""## Original Resume:
{context.original_resume}

## Job Posting:
Title: {job.title}
Company: {job.company}
Requirements: {', '.join(job.requirements)}
Keywords: {', '.join(job.keywords)}
Description: {job.description}
"""

    if context.last_attempt:
        estimate = estimate_content_length(context.last_attempt)
        prompt += f"""
## Last Attempt (Iteration {context.iteration}):
{context.last_attempt}

## Current Content Stats:
- Current: {estimate.chars} chars, {estimate.words} words

NOTE: This is a REFINEMENT iteration. Make the smallest possible change to pass failed filters.
"""

    if context.validation:
        prompt += f"""
## Filter Results:
{context.format_filter_results()}
{HOW_TO_FIX_FILTERS_V2}
IMPORTANT: Make MINIMAL changes to fix ONLY the failed filters.
"""

    prompt += """
Return JSON with:
- html: The HTML body content (no wrapper tags)
- changes: List of changes made
- audit: Audit scores for all 8 dimensions of the OPTIMIZED resume

Output ONLY valid JSON.
"""

    agent = get_optimizer_v2_agent(job, source)
    result = await agent.run(prompt)
    return OptimizedResume(
        html=result.output.html,
        iteration=context.iteration,
        changes=result.output.changes,
        source_checksum=source.checksum,
        audit=result.output.audit,
    )
