"""Compare optimization iteration CAPS (2/3/4/5) under convergence.

Runs ONE cap=MAX_CAP optimization K times per job, capturing the per-iteration
trajectory via a synchronous on_iteration collector, then re-audits each
iteration's HTML to fill quality. The 2/3/4/5 cap outcomes are DERIVED from each
trajectory (exact, because the cap only truncates the loop). See
docs/plans/2026-07-04-caps-comparison-experiment-design.md.

Inputs (local, gitignored): output/Alexander Modestov.pdf, positions.txt.

Run:
    uv run pytest tests/test_caps_comparison.py -s -m benchmark

Skipped unless -m benchmark AND the resume PDF + positions.txt exist AND Vertex
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

from tests.caps_experiment import IterPoint, RunTrajectory, render_caps_report
from tests.test_optimizer_comparison import (
    POSITIONS_PATH,
    RESUME_PATH,
    _bootstrap_vertex,
    _ingest_job,
    _slug,
    _split_positions,
    _with_retry,
    audit_resume_avg,
)

pytestmark = pytest.mark.benchmark

MAX_CAP = 5
REPS = 3
CAPS = (2, 3, 4, 5)


def _make_collector(t0):
    """Sync on_iteration callback: stash raw per-iteration data (no LLM here)."""
    raw = []

    def on_iter(i, optimized, validation):
        raw.append({
            "iteration": i,
            "html": optimized.html,
            "filters_passed": sum(1 for r in validation.results if r.passed),
            "filters_total": len(validation.results),
            "cum_seconds": time.perf_counter() - t0,
        })

    return raw, on_iter


async def _run_trajectory(source, job, job_slug, rep, monkeypatch) -> RunTrajectory:
    """One cap=MAX_CAP run; collect iterations, then re-audit each to build points.

    The final point's best_quality is set from the loop's ACTUAL returned resume
    (`optimized`), not a naive running max: on the success-break path the loop
    returns the current (last) iteration even if an earlier one scored higher, so
    cap>=stop must reflect what the loop really returns. For truncated caps
    (n < stop) the running max is correct, because a success-break before n would
    have stopped the loop at <= n.
    """
    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    t0 = time.perf_counter()
    raw, on_iter = _make_collector(t0)
    with contextlib.redirect_stdout(io.StringIO()):
        optimized, _, _ = await _with_retry(lambda: optimize_for_job(
            source=source, job=job, max_iterations=MAX_CAP,
            on_iteration=on_iter, parallel=True,
        ))

    points = []
    best = -1.0
    for r in raw:
        with contextlib.redirect_stdout(io.StringIO()):
            q, audit = await audit_resume_avg(r["html"], job)
        best = max(best, q)
        points.append(IterPoint(
            iteration=r["iteration"], quality=q, best_quality=best,
            filters_passed=r["filters_passed"], filters_total=r["filters_total"],
            cum_seconds=r["cum_seconds"], audit=audit,
        ))

    # Override the final point's best_quality with the loop's actual return.
    if points:
        with contextlib.redirect_stdout(io.StringIO()):
            ret_q, _ = await audit_resume_avg(optimized.html, job)
        points[-1].best_quality = ret_q

    return RunTrajectory(job_slug=job_slug, rep=rep, points=points)


async def test_caps_comparison(capsys, monkeypatch):
    if not RESUME_PATH.exists():
        pytest.skip(f"resume not found: {RESUME_PATH}")
    if not POSITIONS_PATH.exists():
        pytest.skip(f"positions file not found: {POSITIONS_PATH}")
    project = _bootstrap_vertex()
    if not project:
        pytest.skip("Vertex not configured")
    print(f"Vertex project: {project} ({get_settings().gcp_location})", flush=True)

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    trajs: list[RunTrajectory] = []
    for i, raw in enumerate(jobs_raw, 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            print(f"[{i}/{len(jobs_raw)}] SKIPPED - {type(e).__name__}: {e}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        slug = _slug(label)
        for rep in range(REPS):
            print(f"[{i}/{len(jobs_raw)}] {label} rep {rep + 1}/{REPS} ...", flush=True)
            try:
                traj = await _run_trajectory(source, job, slug, rep, monkeypatch)
                trajs.append(traj)
                print(f"    stopped at iter {traj.stop_iteration}", flush=True)
            except Exception as e:
                print(f"    ERROR {type(e).__name__}: {e}", flush=True)

    assert trajs, "no trajectories collected"
    with capsys.disabled():
        print()
        print(render_caps_report(trajs, caps=CAPS))
