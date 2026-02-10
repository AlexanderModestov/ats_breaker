"""Optimization API routes."""

import asyncio
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response

from hr_breaker.api.deps import CurrentUser, CurrentUserWithEmail, SupabaseServiceDep
from hr_breaker.services.access_control import check_access
from hr_breaker.api.schemas import (
    OptimizationListResponse,
    OptimizationStartResponse,
    OptimizationStatus,
    OptimizationSummary,
    OptimizeRequest,
)
from hr_breaker.config import get_settings, logger
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services import scrape_job_posting, CloudflareBlockedError
from hr_breaker.services.supabase import SupabaseError, SupabaseService
from hr_breaker.agents import parse_job_posting, extract_name

router = APIRouter()


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
        job_text = job_input
        if job_input.startswith("http://") or job_input.startswith("https://"):
            try:
                scrape_start = time.perf_counter()
                job_text = scrape_job_posting(job_input)
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
        job = await parse_job_posting(job_text)
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
        # Extract job_url if job_input looks like a URL
        job_input = run.get("job_input") or ""
        job_url = job_input if job_input.startswith(("http://", "https://")) else None
        summaries.append(
            OptimizationSummary(
                id=run["id"],
                status=run["status"],
                job_title=job_parsed.get("title"),
                job_company=job_parsed.get("company"),
                job_url=job_url,
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

    # Check access before starting
    profile = supabase.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    access = check_access(user_email or "", profile)
    if not access.allowed:
        if access.reason == "trial_exhausted":
            raise HTTPException(
                status_code=402,
                detail="Trial exhausted. Please subscribe to continue."
            )
        elif access.reason == "quota_exhausted":
            raise HTTPException(
                status_code=402,
                detail="Monthly quota exhausted. Purchase an add-on pack or wait for renewal."
            )
        else:
            raise HTTPException(status_code=402, detail="Access denied")

    # Verify CV exists and belongs to user
    cv = supabase.get_cv(request.cv_id, user_id)
    if not cv:
        raise HTTPException(status_code=404, detail="CV not found")

    cv_content = cv.get("content_text")
    if not cv_content:
        raise HTTPException(status_code=400, detail="CV has no extracted text content")

    try:
        # Create optimization run
        run = supabase.create_optimization_run(
            user_id=user_id,
            cv_id=request.cv_id,
            job_input=request.job_input,
        )

        # Consume a request atomically (skip for unlimited users)
        if not access.unlimited:
            is_subscriber = profile.get("subscription_status") == "active"
            settings = get_settings()
            consumed = supabase.consume_request_atomic(
                user_id=user_id,
                is_subscriber=is_subscriber,
                subscription_limit=settings.subscription_request_limit,
            )
            if not consumed:
                raise HTTPException(status_code=402, detail="Failed to consume request")

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

    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{run_id}", response_model=OptimizationStatus)
async def get_optimization_status(
    run_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> OptimizationStatus:
    """Get the status of an optimization run."""
    run = supabase.get_optimization_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    # Extract job_url if job_input looks like a URL
    job_input = run.get("job_input") or ""
    job_url = job_input if job_input.startswith(("http://", "https://")) else None

    return OptimizationStatus(
        id=run["id"],
        status=run["status"],
        current_step=run.get("current_step"),
        iterations=run.get("iterations", 0),
        job_parsed=run.get("job_parsed"),
        job_url=job_url,
        feedback=run.get("feedback"),
        result_html=run.get("result_html"),
        error=run.get("error"),
        timing=run.get("timing"),
        created_at=run["created_at"],
    )


@router.get("/{run_id}/pdf")
async def get_optimization_pdf(
    run_id: str,
    user_id: CurrentUser,
    supabase: SupabaseServiceDep,
) -> Response:
    """Download the result PDF for an optimization run."""
    run = supabase.get_optimization_run(run_id, user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Optimization run not found")

    if run["status"] != "complete":
        raise HTTPException(status_code=400, detail="Optimization not complete")

    pdf_path = run.get("result_pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="No PDF available")

    try:
        pdf_bytes = supabase.download_result_pdf(pdf_path)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=resume_{run_id}.pdf",
            },
        )
    except SupabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
