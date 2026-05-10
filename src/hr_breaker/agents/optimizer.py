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
from hr_breaker.services.length_estimator import estimate_content_length
from hr_breaker.services.renderer import HTMLRenderer, RenderError
from hr_breaker.utils import extract_text_from_html

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"


def _load_resume_guide() -> str:
    """Load the HTML generation guide for the optimizer."""
    guide_path = TEMPLATE_DIR / "resume_guide.md"
    return guide_path.read_text()


OPTIMIZER_PROMPT = r"""
You are a resume optimization expert. Extract content from user's resume and create an optimized HTML resume for a job posting.

INPUT: The user's resume text (any format).

OUTPUT: Generate HTML for the <body> of a resume PDF. Do NOT include <html>, <head>, or <body> tags - only the content.

LANGUAGE RULE (CRITICAL):
- The output resume MUST be in the SAME LANGUAGE as the original resume
- If the original resume is in German, output in German
- If the original resume is in French, output in French
- If the job posting is in a different language than the resume, still output in the resume's original language
- Never translate the resume to another language unless explicitly requested

CONTENT RULES:
- When describing job experiences, show concrete results: focus on impact, not tasks.
- Include specific technologies within achievement descriptions.
- Feature keywords matching job requirements IF they exist in the original resume. You can add umbrella terms if relevant (e.g. if user was making transformer LLM models you can add "NLP")
- Prioritize and highlight experiences most relevant to the role
- If going over the one page limit: remove unrelated content to save space.
- Remove obvious skills (Excel, VS Code, Jupyter, GitHub, Jira) unless specifically required.
- Exclude: location, language proficiency, age, hobbies unless required by job posting.
- Add a summary section highlighting the most relevant experiences.
- Try to preserve the original writing style if possible.
- Avoid leaving an empty space at the bottom of the page if you have useful content to fill.

STRICT RULES - NEVER VIOLATE:
1. NEVER add specific technologies, products, or platforms not in original (e.g. "Amazon Bedrock", "LangChain", "Pinecone")
2. NEVER fabricate job titles, companies, degrees, certifications, or achievements
3. NEVER invent metrics or numbers not in original
4. DO NOT drop work experience or achievements (publications, patents, awards, etc.) unless they decrease fit
5. Never use the em dash symbol, the word "delve" or other common markers of LLM-generated text.
6. NEVER add <script> tags
7. You CAN use <style> tags if you need custom styling beyond the provided classes
8. Do not cut critical content (like work experience, education, etc) if you can cut something else (like summary)
9. NEVER translate the resume - output MUST be in the same language as the original resume
10. NEVER remove a skill, technology, or keyword that IS PRESENT in the original resume — these are not hallucinations even if they look generic. Hallucination = invented; removing real content to "be safe" is the bigger failure mode. If unsure, search the original resume text for the term.

CONTENT BUDGET:
- Target: ~500 words, ~4000 characters (these are rough estimates, actual fit depends on formatting)
- The ONLY authoritative check is page_count from check_content_length

TOOLS:
- Use check_content_length(html) to verify your output fits 1 page BEFORE returning
  - Returns actual page_count from rendered PDF (authoritative)
  - Also returns character/word estimates (rough guidance only)
- If page_count > 1, trim content and check again
- Do not return until check_content_length confirms fits_one_page=true

OPTIONAL TOOLS (use when helpful):
- preview_resume(html) - Renders the PDF and returns a visual preview image. Use ONLY if you suspect layout problems (overflowing columns, awkward gaps, broken sections). Do NOT call routinely — page_count from check_content_length is the authoritative check for fit.
- check_keywords_tool(html) - Returns missing job keywords ranked by TF-IDF importance. Use if unsure about keyword coverage.
- validate_structure(html) - Check HTML has proper headers/sections. Use after major structural changes.

ALLOWED:
- General/umbrella terms inferable from context: "NLP" if they did text processing, "SQL" if they used databases
- Rephrasing metrics with same values: "1% - 10%" -> "1-10%" is fine
- Reordering and emphasizing existing content
- Using content that is commented out and making it visible

LINKS:
- Preserve contacts info as in the original and never delete it
- Preserve all URLs from the original resume (email, LinkedIn, GitHub, website, project links)
- Use full URLs (include https://) for all links

{resume_guide}
"""


# Per-filter playbook. Lives outside the system prompt because it's only
# relevant on refinement iterations (when context.validation is set), so
# attaching it to the user prompt avoids paying its tokens on iter=0.
HOW_TO_FIX_FILTERS = """
HOW TO FIX FAILED FILTERS:
- KeywordMatcher failed → call check_keywords_tool(html) to get missing keywords. For each missing keyword, search the ORIGINAL resume (case-insensitive) — if it appears, surface it in Skills/Summary/relevant bullet. Do NOT invent ones not in the original. Re-run the tool to verify the score moved.
- VectorSimilarityMatcher failed → rephrase Summary and bullet leads with terminology from the job description (only words supported by original experience). Reorder bullets to put job-relevant ones first.
- LLMChecker failed → read the issues line; usually means generic phrasing or LLM-tells (em dash, "delve", "leverage", "robust"). Tighten wording to match original tone.
- ContentIntegrityChecker failed → you removed or paraphrased real facts. Restore them verbatim from the original.
- DataValidator failed → fix HTML structure (missing sections/headers). Run validate_structure(html).
- ContentLengthChecker failed → use check_content_length to confirm; trim from Summary first, then less-relevant bullets, never from headline experience.
"""


class OptimizerResult(BaseModel):
    html: str
    changes: list[str]


def get_optimizer_agent(job: JobPosting, source: ResumeSource) -> Agent:
    """Create optimizer agent with job/source context for filter tools."""
    settings = get_settings()
    resume_guide = _load_resume_guide()
    system_prompt = OPTIMIZER_PROMPT.format(resume_guide=resume_guide)
    agent = Agent(
        f"google-gla:{settings.gemini_pro_model}",
        output_type=OptimizerResult,
        system_prompt=system_prompt,
        model_settings=get_model_settings(),
    )

    @agent.system_prompt
    def add_current_date() -> str:
        return f"Today's date: {date.today().strftime('%B %Y')}"

    # Per-agent cache: WeasyPrint render is the slow part of check_content_length.
    # The LLM often calls the tool 2-3× with identical HTML during one
    # optimize_resume; caching skips the redundant renders.
    _length_cache: dict[str, dict] = {}

    @agent.tool_plain
    def check_content_length(html: str) -> dict:
        """Check if HTML content fits one page by rendering PDF. Call before finalizing."""
        cached = _length_cache.get(html)
        if cached is not None:
            logger.debug("check_content_length cache hit")
            return cached

        est = estimate_content_length(html)

        # Actually render PDF to check real page count
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
            result["suggestion"] = (
                f"Content spans {page_count} pages. Remove ~{est.overflow_words} words (estimate)"
            )
        logger.debug(
            "check_content_length called: %d pages, %d chars, %d words, fits=%s",
            page_count,
            est.chars,
            est.words,
            fits_one_page,
        )
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


async def optimize_resume(
    source: ResumeSource,
    job: JobPosting,
    context: IterationContext,
) -> OptimizedResume:
    """Optimize resume for job posting."""
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
Do NOT rewrite from scratch - modify the last attempt minimally.
"""

    if context.validation:
        prompt += f"""
## Filter Results:
{context.format_filter_results()}
{HOW_TO_FIX_FILTERS}
IMPORTANT: Make MINIMAL changes to fix ONLY the failed filters listed above.
- Start from the Last Attempt HTML above and modify it in place.
- Change ONLY what's needed to move each FAILED filter above its threshold.
- Do NOT regress any PASSED filter — preserve its content and structure.
- Do NOT rewrite, rephrase, or restructure content unrelated to the failures.
- Apply the per-filter actions from the HOW TO FIX FAILED FILTERS section above.
- If a previous iteration's changes did NOT move the failing score, try a different action (e.g. KeywordMatcher: actually add the missing keywords from the original resume into Skills, don't just reword bullets).
"""

    prompt += """
Return JSON with:
- html: The HTML body content (no wrapper tags, just the content for <body>)
- changes: List of changes made (for tracking)

Output ONLY valid JSON. The html field should contain the raw HTML string.
"""

    agent = get_optimizer_agent(job, source)
    result = await agent.run(prompt)
    return OptimizedResume(
        html=result.output.html,
        iteration=context.iteration,
        changes=result.output.changes,
        source_checksum=source.checksum,
    )
