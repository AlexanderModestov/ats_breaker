"""Compare optimization step counts (`max_iterations`) on speed and quality.

Same measurement harness as `test_optimizer_comparison`, but instead of varying
the optimizer version it pins the winning config (v2 + gemini-2.5-flash) and
varies `max_iterations`: 2 vs 3 (current default) vs 4. For each job it runs the
full `optimize_for_job` loop once per step count, then scores each final resume
with one independent 8-dimension auditor (2 runs, averaged) so they sit on the
same ruler. Reuses the comparison module's scoring + report.

Important: `optimize_for_job` early-exits as soon as all filters pass and returns
the best-scoring iteration — `max_iterations` is only a cap. It therefore only
changes the outcome on jobs that never converge. The `iters` column is the
iteration actually selected; compare it to the cap to see whether the cap bit.

Inputs (local, gitignored): `output/Alexander Modestov.pdf`, `positions.txt`.
Outputs: `output/comparison/<job-slug>_s2.pdf`, `_s3.pdf`, `_s4.pdf`.

Run:
    uv run pytest tests/test_steps_comparison.py -s -m benchmark

Skipped unless `-m benchmark` AND the resume PDF + positions.txt exist AND Vertex
credentials are configured.
"""

import contextlib
import io
import time

import pytest

from hr_breaker.config import get_settings
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer

from tests.test_optimizer_comparison import (
    OUTPUT_DIR,
    POSITIONS_PATH,
    RESUME_PATH,
    JobResult,
    VersionResult,
    _bootstrap_vertex,
    _ingest_job,
    _print_report,
    _slug,
    _split_positions,
    _with_retry,
    audit_resume_avg,
)

pytestmark = pytest.mark.benchmark

STEP_COUNTS = (2, 3, 4)
STEP_LABELS = {n: f"s{n}" for n in STEP_COUNTS}


async def _run_steps(
    steps: int, source: ResumeSource, job, label: str, monkeypatch,
    audit_model: str | None = None,
) -> VersionResult:
    """Run the full optimize loop with `max_iterations=steps`, save PDF, audit it."""
    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()
    label_v = STEP_LABELS[steps]

    t = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            optimized, validation, _ = await _with_retry(
                lambda: optimize_for_job(
                    source=source, job=job, max_iterations=steps, parallel=True
                )
            )
        elapsed = time.perf_counter() - t
    except Exception as e:
        return VersionResult(label_v, time.perf_counter() - t, error=f"{type(e).__name__}: {e}")

    res = VersionResult(
        version=label_v,
        total_time=elapsed,
        iterations=optimized.iteration + 1,
        filters_passed=sum(1 for r in validation.results if r.passed),
        filters_total=len(validation.results),
    )

    if optimized.html:
        try:
            pdf_bytes = optimized.pdf_bytes or HTMLRenderer().render(optimized.html).pdf_bytes
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path = OUTPUT_DIR / f"{_slug(label)}_{label_v}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            res.pdf_path = str(pdf_path)
        except Exception as e:
            res.error = f"save_pdf: {type(e).__name__}: {e}"

        try:
            with contextlib.redirect_stdout(io.StringIO()):
                res.quality_avg, res.audit = await audit_resume_avg(
                    optimized.html, job, model=audit_model
                )
        except Exception as e:
            res.error = (res.error + " | " if res.error else "") + f"audit: {type(e).__name__}: {e}"

    return res


async def test_steps_3_vs_4_comparison(capsys, monkeypatch):
    if not RESUME_PATH.exists():
        pytest.skip(f"resume not found: {RESUME_PATH}")
    if not POSITIONS_PATH.exists():
        pytest.skip(f"positions file not found: {POSITIONS_PATH}")
    project = _bootstrap_vertex()
    if not project:
        pytest.skip(
            "Vertex not configured: set GOOGLE_CLOUD_PROJECT / "
            "GOOGLE_APPLICATION_CREDENTIALS, or place the service-account JSON in repo root"
        )
    print(f"Vertex project: {project} ({get_settings().gcp_location})", flush=True)

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    versions = tuple(STEP_LABELS[n] for n in STEP_COUNTS)
    results: list[JobResult] = []
    skipped: list[str] = []
    for i, raw in enumerate(jobs_raw, 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            head = raw.splitlines()[0][:60]
            skipped.append(f"{head} ({type(e).__name__}: {e})")
            print(f"[{i}/{len(jobs_raw)}] SKIPPED {head} - {type(e).__name__}: {e}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        print(f"[{i}/{len(jobs_raw)}] {label} ...", flush=True)

        jr = JobResult(label=label)
        try:
            print("    base: scoring original (2 runs)...", flush=True)
            with contextlib.redirect_stdout(io.StringIO()):
                jr.baseline_quality, jr.baseline = await audit_resume_avg(resume_text, job)
            print(f"    base: {jr.baseline_quality:.0f}% {jr.baseline.overall}", flush=True)
        except Exception as e:
            print(f"    base: error {type(e).__name__}: {e}", flush=True)

        for n in STEP_COUNTS:
            r = await _run_steps(n, source, job, label, monkeypatch)
            jr.by_version[STEP_LABELS[n]] = r
            note = r.error or f"{r.total_time:.1f}s qual={r.quality:.0f}% iters={r.iterations}"
            print(f"    {STEP_LABELS[n]}: {note}", flush=True)
        results.append(jr)

    with capsys.disabled():
        _print_report(results, versions=versions)
        if skipped:
            print()
            print(f"skipped jobs (scrape/parse failed): {len(skipped)}")
            for s in skipped:
                print(f"  - {s}")
