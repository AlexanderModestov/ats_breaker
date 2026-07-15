"""Core optimization loop."""

import asyncio
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from hr_breaker.agents import optimize_resume, optimize_resume_v2, parse_job_posting
from hr_breaker.agents.auditor import audit_resume, audit_to_guidance
from hr_breaker.models.audit import ordinal_sum, no_dim_below_moderate
from hr_breaker.config import get_settings, logger
from hr_breaker.filters import (
    LLMChecker,
    DataValidator,
    FilterRegistry,
    ContentIntegrityChecker,
    KeywordMatcher,
    VectorSimilarityMatcher,
)
from hr_breaker.models import (
    FilterResult,
    IterationContext,
    JobPosting,
    OptimizedResume,
    ResumeSource,
    ValidationResult,
)
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import RenderError, HTMLRenderer

# Ensure filters are registered
_ = DataValidator, LLMChecker, KeywordMatcher, VectorSimilarityMatcher, ContentIntegrityChecker

PATIENCE = 1  # non-improving iterations tolerated before stopping


@contextmanager
def log_time(operation: str):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"  ⏱️  {operation}: {elapsed:.2f}s")


async def run_filters(
    optimized: OptimizedResume,
    job: JobPosting,
    source: ResumeSource,
    parallel: bool = False,
) -> ValidationResult:
    """Run filters, either sequentially (early exit) or in parallel."""
    filters = FilterRegistry.all()

    if parallel:
        # Run all filters concurrently
        print("  🔍 Running filters in parallel...")
        start = time.perf_counter()
        filter_instances = [filter_cls() for filter_cls in filters]
        tasks = [f.evaluate(optimized, job, source) for f in filter_instances]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        print(f"  ⏱️  All filters (parallel): {time.perf_counter() - start:.2f}s")

        # Convert exceptions to failed FilterResults
        results = []
        for f, result in zip(filter_instances, raw_results):
            if isinstance(result, Exception):
                print(f"    ❌ {f.name}: ERROR - {result}")
                results.append(FilterResult(
                    filter_name=f.name,
                    passed=False,
                    score=0.0,
                    threshold=getattr(f, 'threshold', 0.5),
                    issues=[f"Filter error: {type(result).__name__}: {result}"],
                    suggestions=["Check filter implementation"],
                ))
            else:
                status = "✅" if result.passed else "❌"
                print(f"    {status} {f.name}: score={result.score:.2f}")
                results.append(result)
        return ValidationResult(results=results)

    # Sequential mode: sorted by priority, early exit on failure
    print("  🔍 Running filters sequentially...")
    results = []
    filters = sorted(filters, key=lambda f: f.priority)
    total_start = time.perf_counter()

    for filter_cls in filters:
        # Skip high-priority (last) filters if earlier ones failed
        if filter_cls.priority >= 100 and results and not all(r.passed for r in results):
            continue

        f = filter_cls()
        start = time.perf_counter()
        result = await f.evaluate(optimized, job, source)
        elapsed = time.perf_counter() - start
        status = "✅" if result.passed else "❌"
        print(f"    {status} {filter_cls.name}: {elapsed:.2f}s (score={result.score:.2f})")
        results.append(result)

        # Early exit on failure (unless it's a final check)
        if not result.passed and filter_cls.priority < 100:
            print(f"    ⚠️  Early exit: {filter_cls.name} failed")
            break

    print(f"  ⏱️  All filters (sequential): {time.perf_counter() - total_start:.2f}s")
    return ValidationResult(results=results)


async def optimize_for_job(
    source: ResumeSource,
    job_text: str | None = None,
    max_iterations: int | None = None,
    on_iteration: Callable | None = None,
    job: JobPosting | None = None,
    parallel: bool = False,
) -> tuple[OptimizedResume, ValidationResult, JobPosting]:
    """
    Core optimization loop.

    Args:
        source: Source resume
        job_text: Job posting text (required if job not provided)
        max_iterations: Max optimization iterations (default from settings)
        on_iteration: Optional callback(iteration, optimized, validation)
        job: Pre-parsed job posting (optional, skips parsing if provided)

    Returns:
        (optimized_resume, validation_result, job_posting)
    """
    settings = get_settings()
    if max_iterations is None:
        max_iterations = settings.max_iterations

    renderer = HTMLRenderer()

    if job is None:
        if job_text is None:
            raise ValueError("Either job_text or job must be provided")
        with log_time("parse_job_posting"):
            # TODO(url-signal): plumb url here if this branch is ever reached;
            # current callers pre-parse and pass job=, so URL signal flows via that path.
            job, _ = await parse_job_posting(job_text)
    # Audit the original resume to guide the optimizer on what to preserve vs improve.
    audit_guidance: str | None = None
    try:
        with log_time("audit_original"):
            baseline_audit = await audit_resume(source.content, job)
        audit_guidance = audit_to_guidance(baseline_audit)
        print(f"  📋 Baseline audit: {baseline_audit.overall} — guidance ready")
    except Exception as e:
        logger.warning("Baseline audit failed, proceeding without guidance: %s", e)

    optimized = None
    validation = None
    last_attempt: str | None = None
    best_optimized = None
    best_validation = None
    best_q = -1          # best audit ordinal-sum seen so far
    no_improve = 0

    for i in range(max_iterations):
        iter_start = time.perf_counter()
        print(f"\n  {'='*50}")
        print(f"  🔄 ITERATION {i + 1}/{max_iterations}")
        print(f"  {'='*50}")

        ctx = IterationContext(
            iteration=i,
            original_resume=source.content,
            last_attempt=last_attempt,
            validation=validation,
            audit_guidance=audit_guidance,
        )
        with log_time("optimize_resume (LLM)"):
            if settings.optimizer_version == "v2":
                optimized = await optimize_resume_v2(source, job, ctx)
            else:
                optimized = await optimize_resume(source, job, ctx)
        print(f"  📝 Changes: {optimized.changes[:100]}..." if len(optimized.changes) > 100 else f"  📝 Changes: {optimized.changes}")
        # Store last attempt for feedback (html or data depending on mode)
        last_attempt = optimized.html if optimized.html else (
            optimized.data.model_dump_json() if optimized.data else None
        )

        # Render PDF and extract text for filters (like real ATS)
        optimized = _render_and_extract(optimized, renderer)

        if optimized.pdf_text is None:
            # PDF rendering failed - treat as validation failure
            validation = ValidationResult(
                results=[
                    FilterResult(
                        filter_name="PDFRender",
                        passed=False,
                        score=0.0,
                        threshold=1.0,
                        issues=["Failed to render resume to PDF"],
                        suggestions=["Check resume data structure"],
                    )
                ]
            )
        else:
            validation = await run_filters(optimized, job, source, parallel=parallel)

        iter_elapsed = time.perf_counter() - iter_start
        passed_count = sum(1 for r in validation.results if r.passed)
        total_count = len(validation.results)
        print(f"  📊 Iteration {i + 1} result: {passed_count}/{total_count} filters passed")
        print(f"  ⏱️  Iteration {i + 1} total: {iter_elapsed:.2f}s")

        if on_iteration:
            on_iteration(i, optimized, validation)

        # Independent quality audit of THIS iteration's output (trustworthy
        # convergence signal — not the optimizer's self-grade).
        audit = None
        q = None
        if optimized.pdf_text is not None:
            try:
                audit = await audit_resume(optimized.pdf_text, job)
                q = ordinal_sum(audit)
                print(f"  🎯 Audit: {audit.overall} (q={q}/16)")
            except Exception as e:
                logger.warning("Iteration audit failed: %s", e)

        # Track best by audit ordinal-sum; guard convergence with patience.
        improved = q is not None and q > best_q
        if improved or best_optimized is None:
            best_q = q if q is not None else best_q
            best_optimized = optimized
            best_validation = validation
            no_improve = 0

        # Success target: filters pass AND no dimension below Moderate.
        if validation.passed and audit is not None and no_dim_below_moderate(audit):
            print(f"  ✅ Success target met (filters pass, q={q})")
            break

        if not improved and best_optimized is not None:
            no_improve += 1
            print(f"  ⏸️  No improvement ({no_improve}/{PATIENCE} tolerated)")
            if no_improve > PATIENCE:
                print(f"  🛑 Converged — stopping at iteration {i + 1}")
                break

        # Refresh guidance from THIS iteration's audit so the next round is told
        # what this attempt got wrong (was previously frozen at baseline).
        if audit is not None:
            audit_guidance = audit_to_guidance(audit)

    if best_optimized is not optimized:
        print(f"  ↩️  Returning best iteration (q={best_q}) — last was worse")

    return best_optimized, best_validation, job


def _render_and_extract(optimized: OptimizedResume, renderer) -> OptimizedResume:
    """Render PDF and extract text, updating the OptimizedResume."""
    try:
        with log_time("render_pdf"):
            # Use html if available, otherwise fall back to data (legacy)
            if optimized.html is not None:
                result = renderer.render(optimized.html)
            elif optimized.data is not None:
                result = renderer.render_data(optimized.data)
            else:
                raise RenderError("No content to render (neither html nor data)")

        # Extract text from rendered PDF
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(result.pdf_bytes)
            pdf_path = Path(f.name)

        try:
            with log_time("extract_text_from_pdf"):
                pdf_text = extract_text_from_pdf(pdf_path)
        finally:
            pdf_path.unlink()

        return optimized.model_copy(
            update={"pdf_text": pdf_text, "pdf_bytes": result.pdf_bytes}
        )
    except RenderError as e:
        logger.error(f"Render error: {e}")
        return optimized
