"""Resume editor API routes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from hr_breaker.api.deps import CurrentUser, SupabaseServiceDep
from hr_breaker.models import JobPosting, OptimizedResume, ResumeSource
from hr_breaker.models.editor import RequirementItem
from hr_breaker.services.requirements_matcher import match_requirements
from hr_breaker.services.patch_applier import apply_patches
from hr_breaker.agents.resume_editor import edit_resume
from hr_breaker.filters import ContentLengthChecker, KeywordMatcher

router = APIRouter()


# --- Request/Response schemas ---


class EditRequest(BaseModel):
    instruction: str
    html: str


class EditResponse(BaseModel):
    patches: list[dict]
    updated_html: str


class ValidateRequest(BaseModel):
    html: str


class ValidateResponse(BaseModel):
    results: list[dict]
    requirements: list[RequirementItem]


class RequirementsResponse(BaseModel):
    requirements: list[RequirementItem]


# --- Helper ---


def _get_completed_run(run_id: str, user_id: str, supabase) -> dict:
    """Fetch an optimization run and verify it is complete."""
    run = supabase.get_optimization_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Optimization not complete")
    return run


# --- Endpoints ---


@router.get("/{run_id}/requirements", response_model=RequirementsResponse)
async def get_requirements(
    run_id: str, user_id: CurrentUser, supabase: SupabaseServiceDep
):
    """Return job requirements matched against the optimized resume."""
    run = _get_completed_run(run_id, user_id, supabase)
    job = JobPosting.model_validate(run["job_parsed"])
    html = run.get("result_html", "")
    items = match_requirements(job, html)
    return RequirementsResponse(requirements=items)


@router.post("/{run_id}/edit", response_model=EditResponse)
async def edit_resume_endpoint(
    run_id: str,
    req: EditRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Apply an LLM-driven edit to the resume HTML."""
    run = _get_completed_run(run_id, user_id, supabase)

    # Get original resume text for hallucination prevention
    cv_id = run.get("cv_id")
    original = ""
    if cv_id:
        cv = supabase.get_cv(cv_id, user_id)
        if cv:
            original = cv.get("content_text", "") or ""

    result = await edit_resume(req.html, original, req.instruction)
    updated_html = apply_patches(req.html, result.patches)

    return EditResponse(
        patches=[p.model_dump() for p in result.patches],
        updated_html=updated_html,
    )


@router.post("/{run_id}/validate", response_model=ValidateResponse)
async def validate_resume(
    run_id: str,
    req: ValidateRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Run lightweight filters on edited resume HTML."""
    run = _get_completed_run(run_id, user_id, supabase)
    job = JobPosting.model_validate(run["job_parsed"])

    source = ResumeSource(content="", checksum="")
    optimized = OptimizedResume(
        html=req.html, iteration=0, changes=[], source_checksum=""
    )

    results = []
    for filter_cls in [ContentLengthChecker, KeywordMatcher]:
        f = filter_cls()
        result = await f.evaluate(optimized, job, source)
        results.append(result.model_dump())

    requirements = match_requirements(job, req.html)
    return ValidateResponse(results=results, requirements=requirements)


class DownloadRequest(BaseModel):
    html: str


@router.post("/{run_id}/download")
async def download_edited_pdf(
    run_id: str,
    req: DownloadRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
):
    """Render edited resume HTML to PDF and return it."""
    _get_completed_run(run_id, user_id, supabase)

    from hr_breaker.services.renderer import HTMLRenderer

    renderer = HTMLRenderer()
    result = renderer.render(req.html)
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=resume_{run_id}.pdf"
        },
    )
