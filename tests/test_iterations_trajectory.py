"""Origin CV vs N optimization passes on ONE trajectory.

Unlike the capped sweep (`test_steps_comparison`, which runs three independent
runs capped at 2/3/4), this runs a SINGLE optimization trajectory per job and
snapshots the CV after each pass — so pass N is genuinely pass N-1 plus one more
refinement (same run, evolving guidance + filter feedback). That isolates the
marginal value of each additional iteration, free of the cross-run LLM noise that
made the capped sweep's per-step averages hard to read.

The loop below mirrors `orchestration.optimize_for_job` MINUS its two stop
conditions (success-target break + patience) so all PASSES iterations always run.
Keep in sync if that loop changes. Config pinned to the winner: v2 + flash.

Each snapshot (and the original) is scored by the independent 8-dimension auditor,
2 runs averaged, same ruler as the other comparison tests.

Inputs (local, gitignored): `output/Alexander Modestov.pdf`, `positions.txt`.
Outputs: `output/comparison/<job-slug>_iter{1..4}.pdf`.

Run:
    uv run pytest tests/test_iterations_trajectory.py -s -m benchmark
"""

import contextlib
import io
import statistics
import sys
import time
from dataclasses import dataclass, field

import pytest

from hr_breaker.agents import optimize_resume_v2
from hr_breaker.agents.auditor import audit_to_guidance
from hr_breaker.config import get_settings
from hr_breaker.models import FilterResult, IterationContext, ResumeSource, ValidationResult
from hr_breaker.orchestration import _render_and_extract, run_filters
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer

from tests.test_optimizer_comparison import (
    OUTPUT_DIR,
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

PASSES = 4


@dataclass
class Snapshot:
    passes: int  # 1..PASSES (0 = original)
    quality: float
    overall: str
    pass_time: float = 0.0


@dataclass
class JobTrajectory:
    label: str
    base_quality: float | None = None
    base_overall: str | None = None
    snaps: list[Snapshot] = field(default_factory=list)
    error: str | None = None


async def _run_trajectory(source: ResumeSource, job, label: str, monkeypatch) -> JobTrajectory:
    """One optimize trajectory, forced to PASSES iterations, auditing each snapshot."""
    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    traj = JobTrajectory(label=label)
    renderer = HTMLRenderer()

    # Original CV (pass 0): audit + seed the optimizer guidance, like optimize_for_job.
    base_q, base_audit = await audit_resume_avg(source.content, job)
    traj.base_quality, traj.base_overall = base_q, base_audit.overall
    guidance = audit_to_guidance(base_audit)

    last_attempt = None
    validation = None
    for i in range(PASSES):
        t = time.perf_counter()
        ctx = IterationContext(
            iteration=i,
            original_resume=source.content,
            last_attempt=last_attempt,
            validation=validation,
            audit_guidance=guidance,
        )
        optimized = await _with_retry(lambda: optimize_resume_v2(source, job, ctx))
        last_attempt = optimized.html if optimized.html else (
            optimized.data.model_dump_json() if optimized.data else None
        )
        optimized = _render_and_extract(optimized, renderer)
        if optimized.pdf_text is None:
            validation = ValidationResult(results=[FilterResult(
                filter_name="PDFRender", passed=False, score=0.0, threshold=1.0,
                issues=["Failed to render resume to PDF"], suggestions=["Check resume data structure"],
            )])
        else:
            validation = await run_filters(optimized, job, source, parallel=True)
        pass_time = time.perf_counter() - t

        # Report audit (2-run avg) on the rendered HTML; reuse its AuditScore to
        # refresh guidance for the next pass (faithful to the production loop).
        q_avg, audit = await audit_resume_avg(optimized.html, job)
        traj.snaps.append(Snapshot(passes=i + 1, quality=q_avg, overall=audit.overall, pass_time=pass_time))
        guidance = audit_to_guidance(audit)

        if optimized.pdf_bytes:
            with contextlib.suppress(Exception):
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUTPUT_DIR / f"{_slug(label)}_iter{i + 1}.pdf").write_bytes(optimized.pdf_bytes)

    return traj


def _print_report(trajs: list[JobTrajectory]) -> None:
    cols = ["origin"] + [f"iter{n}" for n in range(1, PASSES + 1)]
    print()
    print(f"{'job':<34}" + "".join(f"{c:>9}" for c in cols))
    print("-" * (34 + 9 * len(cols)))
    for tr in trajs:
        if tr.error:
            print(f"{tr.label[:32]:<34}  {tr.error[:60]}")
            continue
        vals = [tr.base_quality] + [s.quality for s in tr.snaps]
        cells = "".join(f"{v:>8.0f}%" if v is not None else f"{'-':>9}" for v in vals)
        print(f"{tr.label[:32]:<34}{cells}")

    # Aggregate mean quality per stage (only jobs that completed all passes).
    full = [tr for tr in trajs if not tr.error and tr.base_quality is not None and len(tr.snaps) == PASSES]
    print()
    print(f"=== aggregates (n={len(full)} complete trajectories) ===")
    if not full:
        print("no complete trajectories")
        return
    stage_means = [statistics.mean(tr.base_quality for tr in full)]
    stage_means += [statistics.mean(tr.snaps[k].quality for tr in full) for k in range(PASSES)]
    print(f"{'stage':<10}{'mean_qual':>11}{'marginal d':>13}")
    print("-" * 34)
    for idx, (name, m) in enumerate(zip(cols, stage_means)):
        d = "" if idx == 0 else f"{m - stage_means[idx - 1]:>+11.0f}%"
        print(f"{name:<10}{m:>10.0f}%{d:>13}")
    print(f"\ntotal origin->iter{PASSES}: {stage_means[-1] - stage_means[0]:+.0f}%")

    # Mean wall-time per pass.
    print()
    print(f"{'pass':<10}{'mean_time':>11}")
    print("-" * 21)
    for k in range(PASSES):
        ts = [tr.snaps[k].pass_time for tr in full]
        print(f"iter{k + 1:<6}{statistics.mean(ts):>9.0f}s")


async def test_origin_vs_iterations_trajectory(capsys, monkeypatch):
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if not RESUME_PATH.exists():
        pytest.skip(f"resume not found: {RESUME_PATH}")
    if not POSITIONS_PATH.exists():
        pytest.skip(f"positions file not found: {POSITIONS_PATH}")
    project = _bootstrap_vertex()
    if not project:
        pytest.skip("Vertex not configured")
    print(f"Vertex project: {project} ({get_settings().gcp_location})  PASSES={PASSES}", flush=True)

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    trajs: list[JobTrajectory] = []
    skipped: list[str] = []
    for i, raw in enumerate(jobs_raw, 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            head = raw.splitlines()[0][:60]
            skipped.append(f"{head} ({type(e).__name__})")
            print(f"[{i}/{len(jobs_raw)}] SKIPPED {head} - {type(e).__name__}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        print(f"[{i}/{len(jobs_raw)}] {label} ...", flush=True)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                tr = await _run_trajectory(source, job, label, monkeypatch)
            trajs.append(tr)
            line = " ".join(f"i{s.passes}={s.quality:.0f}%" for s in tr.snaps)
            print(f"    base={tr.base_quality:.0f}% {line}", flush=True)
        except Exception as e:
            trajs.append(JobTrajectory(label=label, error=f"{type(e).__name__}: {e}"))
            print(f"    ERROR {type(e).__name__}: {e}", flush=True)

    with capsys.disabled():
        _print_report(trajs)
        if skipped:
            print(f"\nskipped jobs: {len(skipped)}")
            for s in skipped:
                print(f"  - {s}")
