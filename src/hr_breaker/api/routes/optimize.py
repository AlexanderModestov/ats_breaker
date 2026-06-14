"""Optimization API routes."""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response

from hr_breaker.api.deps import (
    CurrentUser,
    CurrentUserWithEmail,
    SupabaseServiceDep,
    get_profile_or_404,
    get_run_or_404,
    require_feature,
)
from hr_breaker.services.access_control import check_optimization_quota, _is_unlimited
from hr_breaker.services.tiers import Feature, optimization_limit
from hr_breaker.api.schemas import (
    JobPatchRequest,
    OptimizationListResponse,
    OptimizationStartResponse,
    OptimizationStatus,
    OptimizationSummary,
    OptimizeRequest,
)
from hr_breaker.analytics import capture
from hr_breaker.config import get_settings, logger
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services import scrape_job_posting, CloudflareBlockedError
from hr_breaker.services.supabase import SupabaseError, SupabaseService
from hr_breaker.agents import parse_job_posting, extract_name

router = APIRouter(dependencies=[Depends(require_feature(Feature.OPTIMIZE))])


def _extract_job_url(job_input: str | None) -> str | None:
    """Return the job input as a URL if it looks like one, else None."""
    job_input = job_input or ""
    return job_input if job_input.startswith(("http://", "https://")) else None


def _run_to_status(run: dict, job_parsed: dict | None) -> OptimizationStatus:
    """Build an OptimizationStatus response from a stored run row."""
    return OptimizationStatus(
        id=run["id"],
        status=run["status"],
        current_step=run.get("current_step"),
        iterations=run.get("iterations", 0),
        job_parsed=job_parsed,
        job_url=_extract_job_url(run.get("job_input")),
        first_name=run.get("first_name"),
        last_name=run.get("last_name"),
        feedback=run.get("feedback"),
        result_html=run.get("result_html"),
        error=run.get("error"),
        timing=run.get("timing"),
        created_at=run["created_at"],
    )


async def _run_optimization(
    run_id: str,
    user_id: str,
    cv_content: str,
    job_input: str,
    max_iterations: int,
    parallel: bool,
    supabase: SupabaseService,
) -> None:
    """Background task to run the optimization."""
    settings = get_settings()
    total_start = time.perf_counter()
    timing: dict[str, float] = {}
    print(f"\n{'='*60}")
    print(f"[{run_id}] OPTIMIZATION STARTED")
    print(f"{'='*60}")

    try:
        # Step 1: Parse job posting
        supabase.update_optimization_run(run_id, {
            "status": "parse_job",
            "current_step": "Fetching and parsing job posting...",
        })

        # Check if job_input is a URL or text
        job_url = _extract_job_url(job_input)
        job_text = job_input
        job_hints = None
        if job_url:
            try:
                scrape_start = time.perf_counter()
                scraped = scrape_job_posting(job_url)
                job_text = scraped.text
                job_hints = scraped.hints
                timing["scrape_job"] = time.perf_counter() - scrape_start
                print(f"⏱️  Scrape job: {timing['scrape_job']:.2f}s")
            except CloudflareBlockedError:
                supabase.update_optimization_run(run_id, {
                    "status": "failed",
                    "current_step": None,
                    "error": "Failed to fetch job posting: protected by Cloudflare. Please paste the job text instead.",
                })
                return
            except Exception as e:
                supabase.update_optimization_run(run_id, {
                    "status": "failed",
                    "current_step": None,
                    "error": f"Failed to fetch job posting: {e}",
                })
                return

        # Parse job posting
        parse_start = time.perf_counter()
        print(f"📋 Parsing job posting...")
        job, needs_review = await parse_job_posting(job_text, url=job_url, hints=job_hints)
        timing["parse_job"] = time.perf_counter() - parse_start
        print(f"⏱️  Parse job: {timing['parse_job']:.2f}s - {job.title} at {job.company}")
        logger.info(f"[{run_id}] Job parsed: {job.title} at {job.company}")
        job_parsed = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "requirements": job.requirements,
            "responsibilities": job.responsibilities,
            "keywords": job.keywords,
            "needs_review": needs_review,
        }

        supabase.update_optimization_run(run_id, {
            "status": "generate",
            "current_step": f"Optimizing resume for {job.title} at {job.company}...",
            "job_parsed": job_parsed,
        })

        # Step 2: Extract name from CV and create ResumeSource
        name_start = time.perf_counter()
        print(f"👤 Extracting name from CV...")
        first_name, last_name = await extract_name(cv_content)
        timing["extract_name"] = time.perf_counter() - name_start
        print(f"⏱️  Extract name: {timing['extract_name']:.2f}s - {first_name} {last_name}")
        source = ResumeSource(
            content=cv_content,
            first_name=first_name,
            last_name=last_name,
        )
        supabase.update_optimization_run(run_id, {
            "first_name": first_name,
            "last_name": last_name,
        })

        capture(user_id, "optimization_started", {
            "job_title": job.title,
            "job_company": job.company,
            "max_iterations": max_iterations,
            "parallel": parallel,
            "source": "api",
        })

        # Track feedback from each iteration
        all_feedback: list[dict[str, Any]] = []

        def on_iteration(iteration: int, optimized: Any, validation: Any) -> None:
            """Callback for each optimization iteration."""
            iteration_feedback = {
                "iteration": iteration + 1,
                "passed": validation.passed,
                "results": [
                    {
                        "filter_name": r.filter_name,
                        "passed": r.passed,
                        "score": r.score,
                        "threshold": r.threshold,
                        "issues": r.issues,
                        "suggestions": r.suggestions,
                    }
                    for r in validation.results
                ],
            }
            all_feedback.append(iteration_feedback)

            status = "validate" if iteration == 0 else "refine"
            supabase.update_optimization_run(run_id, {
                "status": status,
                "current_step": f"Iteration {iteration + 1}: {'Passed' if validation.passed else 'Refining'}...",
                "iterations": iteration + 1,
                "feedback": all_feedback,
            })

        # Step 3-5: Run optimization loop
        loop_start = time.perf_counter()
        print(f"🔄 Starting optimization loop (max {max_iterations} iterations)...")
        optimized, validation, _ = await optimize_for_job(
            source=source,
            job=job,
            max_iterations=max_iterations,
            on_iteration=on_iteration,
            parallel=parallel,
        )
        timing["optimization_loop"] = time.perf_counter() - loop_start
        timing["total"] = time.perf_counter() - total_start

        capture(user_id, "optimization_completed", {
            "job_title": job.title,
            "job_company": job.company,
            "passed": validation.passed,
            "iterations": len(all_feedback),
            "duration_seconds": round(timing["total"], 2),
            "source": "api",
        })

        # Step 6: Save result
        print(f"\n{'='*60}")
        print(f"📊 OPTIMIZATION COMPLETE")
        print(f"{'='*60}")
        print(f"⏱️  Optimization loop: {timing['optimization_loop']:.2f}s")
        print(f"⏱️  Total time: {timing['total']:.2f}s")
        print(f"✅ Passed: {validation.passed}")
        result_html = optimized.html if optimized else None
        result_pdf_path = None

        if optimized and optimized.pdf_bytes:
            try:
                result_pdf_path = supabase.upload_result_pdf(run_id, user_id, optimized.pdf_bytes)
            except SupabaseError as e:
                logger.error(f"Failed to upload result PDF: {e}")

        logger.info(f"[{run_id}] Saving results to database...")
        supabase.update_optimization_run(run_id, {
            "status": "complete",
            "current_step": None,
            "result_html": result_html,
            "result_pdf_path": result_pdf_path,
            "feedback": all_feedback,
            "timing": timing,
            "audit": optimized.audit.model_dump() if optimized and optimized.audit else None,
        })
        logger.info(f"[{run_id}] Optimization complete! Timing: {timing}")

    except Exception as e:
        logger.exception(f"Optimization failed: {e}")
        supabase.update_optimization_run(run_id, {
            "status": "failed",
            "current_step": None,
            "error": str(e),
        })


@router.get("", response_model=OptimizationListResponse)
async def list_optimization_runs(
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationListResponse:
    """List all optimization runs for the current user."""
    runs = supabase.list_optimization_runs(user_id)

    summaries = []
    for run in runs:
        job_parsed = run.get("job_parsed") or {}
        job_url = _extract_job_url(run.get("job_input"))
        summaries.append(
            OptimizationSummary(
                id=run["id"],
                status=run["status"],
                job_title=job_parsed.get("title"),
                job_company=job_parsed.get("company"),
                job_url=job_url,
                needs_review=job_parsed.get("needs_review") or [],
                created_at=run["created_at"],
            )
        )

    return OptimizationListResponse(runs=summaries)


@router.post("", response_model=OptimizationStartResponse)
async def start_optimization(
    request: OptimizeRequest,
    user: CurrentUserWithEmail,
    supabase: SupabaseServiceDep,
    background_tasks: BackgroundTasks,
) -> OptimizationStartResponse:
    """Start a new optimization run."""
    user_id, user_email = user

    profile = get_profile_or_404(supabase, user_id)

    quota = check_optimization_quota(user_email or "", profile)
    if not quota.allowed:
        raise HTTPException(status_code=402, detail=quota.to_dict())

    # Verify CV exists and belongs to user
    cv = supabase.get_cv(request.cv_id, user_id)
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")

    cv_content = cv.get("content_text")
    if not cv_content:
        raise HTTPException(status_code=400, detail="CV has no extracted text content")

    # Atomically consume quota before creating the run (admins bypass).
    if not _is_unlimited(user_email or ""):
        ok = supabase.consume_optimization_quota(user_id, optimization_limit(profile))
        if not ok:
            raise HTTPException(
                status_code=402,
                detail={"allowed": False, "remaining": 0, "reason": "quota_exhausted"},
            )

    # Create optimization run
    run = supabase.create_optimization_run(
        user_id=user_id,
        cv_id=request.cv_id,
        job_input=request.job_input,
    )

    # Start background task
    background_tasks.add_task(
        _run_optimization,
        run_id=run["id"],
        user_id=user_id,
        cv_content=cv_content,
        job_input=request.job_input,
        max_iterations=request.max_iterations,
        parallel=request.parallel,
        supabase=supabase,
    )

    return OptimizationStartResponse(run_id=run["id"], status="pending")


@router.get("/{run_id}", response_model=OptimizationStatus)
async def get_optimization_status(
    run_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationStatus:
    """Get the status of an optimization run."""
    run = get_run_or_404(supabase, run_id, user_id)
    return _run_to_status(run, run.get("job_parsed"))


@router.get("/{run_id}/pdf")
async def get_optimization_pdf(
    run_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> Response:
    """Download the result PDF for an optimization run."""
    run = get_run_or_404(supabase, run_id, user_id)

    if run["status"] != "complete":
        raise HTTPException(status_code=400, detail="Optimization not complete")

    pdf_path = run.get("result_pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="No PDF available")

    pdf_bytes = supabase.download_result_pdf(pdf_path)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=resume_{run_id}.pdf",
        },
    )


@router.delete("/{run_id}")
async def delete_optimization(
    run_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> dict[str, bool]:
    """Delete an optimization run."""
    run = get_run_or_404(supabase, run_id, user_id)

    # Delete the PDF from storage if it exists
    pdf_path = run.get("result_pdf_path")
    if pdf_path:
        try:
            supabase.delete_result_pdf(pdf_path)
        except SupabaseError:
            pass  # Ignore storage deletion errors

    # Delete the optimization run record
    supabase.delete_optimization_run(run_id)
    return {"success": True}


@router.patch("/{run_id}/job", response_model=OptimizationStatus)
async def update_optimization_job(
    run_id: str,
    request: JobPatchRequest,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationStatus:
    """Manually fix parsed title/company when the parser failed.

    Updates only labels in `job_parsed` — does not re-run optimization.
    """
    run = get_run_or_404(supabase, run_id, user_id)

    if run["status"] in ("pending", "parse_job"):
        raise HTTPException(
            status_code=409, detail="Job is still being parsed; try again shortly"
        )

    job_parsed = dict(run.get("job_parsed") or {})
    needs_review = list(job_parsed.get("needs_review") or [])

    if request.title is not None:
        job_parsed["title"] = request.title
        if "title" in needs_review:
            needs_review.remove("title")
    if request.company is not None:
        job_parsed["company"] = request.company
        if "company" in needs_review:
            needs_review.remove("company")

    job_parsed["needs_review"] = needs_review
    supabase.update_optimization_run(run_id, {"job_parsed": job_parsed})

    return _run_to_status(run, job_parsed)
