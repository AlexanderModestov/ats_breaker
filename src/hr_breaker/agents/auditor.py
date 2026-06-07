"""Independent resume quality auditor — 8-dimension scoring and optimizer guidance."""

from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.models.audit import AuditScore
from hr_breaker.models.job_posting import JobPosting
from hr_breaker.utils.html_text import extract_text_from_html
from pydantic_ai import Agent

AUDIT_PROMPT = r"""
You are a resume reviewer. You are given a FINISHED resume and a job posting.
Rate the resume across all 8 dimensions below for THIS specific job. Do NOT rewrite
or suggest HTML — only score. Be honest: if a dimension is Weak, say Weak.

1. ATS COMPATIBILITY (ATS-Ready / ATS-Risky / ATS-Broken)
   - Standard section headers ("Professional Experience", "Education", "Skills")
   - No tables, columns, text boxes, or graphics
   - Contact info in the body, target-role keywords present in the body

2. RECRUITER SCAN (Strong / Moderate / Weak) — 7-second F-pattern
   - Name and current title prominent; quantified achievement as first bullet of each role
   - Bullets not paragraphs; gaps present but not over-explained

3. BULLET QUALITY (Strong / Moderate / Weak)
   - XYZ formula ("Accomplished X measured by Y by doing Z"); passes the "so what?" test
   - Quantified (hard or proxy metrics); varied action verbs
   - Avoids "responsible for", "helped with", "worked on"

4. SENIORITY CALIBRATION (Aligned / Mismatched)
   - Verb tier matches candidate's evident level (IC/Manager/Director/VP+)
   - Impact scope grows across roles

5. KEYWORD COVERAGE (Strong / Moderate / Weak)
   - Job-posting keywords present in the body; skills ordered by relevance; specific beats generic

6. STRUCTURE (Strong / Moderate / Weak)
   - Single column; Summary -> Experience -> Education -> Skills; ~1 page; hooking 2-3 line summary

7. CONCERN MANAGEMENT (Strong / Moderate / Weak / NA)
   - Gaps framed neutrally; short tenures get a one-line rationale; career switch bridged
   - Use "NA" only if the resume presents no gaps, short tenures, or switches

8. CONSISTENCY (Strong / Moderate / Weak)
   - Tense (present current / past prior), punctuation, no first person, consistent dates

overall: Strong / Needs Work / Weak — holistic fit of this resume for this job.
top_fixes: the 3 highest-impact remaining improvements, priority-ordered.
"""

_STRONG_VALUES = {"ATS-Ready", "Aligned", "Strong"}

_DIM_LABELS = {
    "ats_compatibility": "ATS compatibility",
    "recruiter_scan": "recruiter scan",
    "bullet_quality": "bullet quality",
    "seniority_calibration": "seniority calibration",
    "keyword_coverage": "keyword coverage",
    "structure": "structure",
    "concern_management": "concern management",
    "consistency": "consistency",
}


def get_auditor_agent(model: str | None = None) -> Agent:
    settings = get_settings()
    return Agent(
        f"google-vertex:{model or settings.optimization_model}",
        output_type=AuditScore,
        system_prompt=AUDIT_PROMPT,
        model_settings=get_model_settings(),
    )


async def audit_resume(
    text_or_html: str, job: JobPosting, model: str | None = None
) -> AuditScore:
    """Score a resume against a job posting on the 8-dimension rubric."""
    resume_text = extract_text_from_html(text_or_html) if "<" in text_or_html else text_or_html
    prompt = f"""## Job Posting
Title: {job.title}
Company: {job.company}
Requirements: {', '.join(job.requirements)}
Keywords: {', '.join(job.keywords)}
Description: {job.description}

## Finished Resume (rendered text)
{resume_text}

Rate this finished resume across all 8 dimensions for this job."""
    result = await get_auditor_agent(model=model).run(prompt)
    return result.output


def audit_to_guidance(audit: AuditScore) -> str:
    """Convert an AuditScore into optimizer guidance (preserve vs improve)."""
    preserve, improve = [], []
    for dim, label in _DIM_LABELS.items():
        val = getattr(audit, dim)
        if val == "NA":
            continue
        (preserve if val in _STRONG_VALUES else improve).append(label)

    lines = ["QUALITY BASELINE (from independent audit of original resume):"]
    if preserve:
        lines.append(f"  Already strong — do NOT regress: {', '.join(preserve)}")
    if improve:
        lines.append(f"  Needs improvement — prioritize fixing: {', '.join(improve)}")
    if audit.top_fixes:
        lines.append("  Top fixes identified:")
        for fix in audit.top_fixes[:3]:
            lines.append(f"    - {fix}")
    return "\n".join(lines)
