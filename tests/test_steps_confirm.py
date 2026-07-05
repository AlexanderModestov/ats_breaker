"""Confirmation run: 2 vs 3 steps with REPEATS optimize runs per job.

The 2/3/4 sweep (`test_steps_comparison`) sampled each (job, step) once, so its
per-step quality averages were swamped by LLM nondeterminism. This test pins the
winning config (v2 + gemini-2.5-flash) and, for each job, runs the full optimize
loop REPEATS times at `max_iterations=2` and REPEATS times at `max_iterations=3`,
auditing each result once. It reports the quality *distribution* (mean / min /
max) and mean time per step so 2-vs-3 can be judged against the noise before
changing the production default. 4 is dropped — the sweep already showed it costs
time without buying quality.

Run:
    uv run pytest tests/test_steps_confirm.py -s -m benchmark
"""

import contextlib
import io
import statistics
import sys
import time

import pytest

from hr_breaker.agents.auditor import audit_resume
from hr_breaker.config import get_settings
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services.pdf_parser import extract_text_from_pdf

from tests.test_optimizer_comparison import (
    POSITIONS_PATH,
    RESUME_PATH,
    _bootstrap_vertex,
    _ingest_job,
    _split_positions,
    _with_retry,
    quality_score,
)

pytestmark = pytest.mark.benchmark

STEPS = (2, 3)
REPEATS = 3


async def _one_run(steps: int, source: ResumeSource, job, monkeypatch):
    """One optimize loop at `max_iterations=steps`, audited once. -> (time, quality|None, err|None)."""
    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    t = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            optimized, _, _ = await _with_retry(
                lambda: optimize_for_job(
                    source=source, job=job, max_iterations=steps, parallel=True
                )
            )
            if not optimized.html:
                return time.perf_counter() - t, None, "no html"
            audit = await _with_retry(lambda: audit_resume(optimized.html, job))
        return time.perf_counter() - t, quality_score(audit), None
    except Exception as e:
        return time.perf_counter() - t, None, f"{type(e).__name__}: {e}"


def _fmt(vals: list[float]) -> str:
    if not vals:
        return "—"
    if len(vals) == 1:
        return f"{vals[0]:.0f}"
    return f"{statistics.mean(vals):.0f} ({min(vals):.0f}-{max(vals):.0f})"


def _print_report(rows: list[dict], baselines: dict[str, float]) -> None:
    print()
    print(f"{'job':<34}{'step':<6}{'n':>3}{'mean_t':>9}{'qual mean(min-max)':>22}")
    print("-" * 74)
    pooled_q = {s: [] for s in STEPS}
    pooled_t = {s: [] for s in STEPS}
    for r in rows:
        base = baselines.get(r["label"])
        base_str = f"  base={base:.0f}%" if base is not None else ""
        print(f"{r['label'][:32]:<34}{'':<6}{'':>3}{'':>9}{base_str}")
        for s in STEPS:
            qs = r["quality"][s]
            ts = r["time"][s]
            errs = r["errors"][s]
            pooled_q[s].extend(qs)
            pooled_t[s].extend(ts)
            note = f"  ({len(errs)} err)" if errs else ""
            mean_t = f"{statistics.mean(ts):.0f}s" if ts else "—"
            print(f"{'':<34}{f's{s}':<6}{len(qs):>3}{mean_t:>9}{_fmt(qs):>22}{note}")

    print()
    print("=== pooled across jobs ===")
    print(f"{'step':<6}{'n':>4}{'mean_t':>9}{'mean_qual':>11}{'min':>6}{'max':>6}")
    print("-" * 42)
    for s in STEPS:
        qs, ts = pooled_q[s], pooled_t[s]
        if not qs:
            print(f"s{s:<5}{'no data':<20}")
            continue
        print(
            f"s{s:<5}{len(qs):>4}{statistics.mean(ts):>8.0f}s"
            f"{statistics.mean(qs):>10.0f}%{min(qs):>6.0f}{max(qs):>6.0f}"
        )

    # Paired per-job comparison: mean(s3) - mean(s2), only where both have data.
    print()
    print("=== paired per-job: mean q(s3) - mean q(s2), mean t(s2) vs t(s3) ===")
    dq = []
    for r in rows:
        q2, q3 = r["quality"][2], r["quality"][3]
        if not q2 or not q3:
            continue
        d = statistics.mean(q3) - statistics.mean(q2)
        dq.append(d)
        print(
            f"  {r['label'][:40]:<42}dqual={d:>+5.0f}%   "
            f"t: {statistics.mean(r['time'][2]):.0f}s -> {statistics.mean(r['time'][3]):.0f}s"
        )
    if dq:
        print(f"\n  mean dqual (s3 - s2) across {len(dq)} jobs: {statistics.mean(dq):+.1f}%")


async def test_steps_2_vs_3_confirm(capsys, monkeypatch):
    # Windows console defaults to cp1252, which crashes on non-ASCII job titles
    # (e.g. Cyrillic). Make stdout/stderr tolerant so the report can't blow up.
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
    print(f"Vertex project: {project} ({get_settings().gcp_location})  REPEATS={REPEATS}", flush=True)

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    rows: list[dict] = []
    baselines: dict[str, float] = {}
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
                baselines[label] = quality_score(await _with_retry(lambda: audit_resume(resume_text, job)))
        except Exception:
            pass

        row = {
            "label": label,
            "quality": {s: [] for s in STEPS},
            "time": {s: [] for s in STEPS},
            "errors": {s: [] for s in STEPS},
        }
        for s in STEPS:
            for rep in range(REPEATS):
                t, q, err = await _one_run(s, source, job, monkeypatch)
                row["time"][s].append(t)
                if q is not None:
                    row["quality"][s].append(q)
                else:
                    row["errors"][s].append(err)
                tag = f"{q:.0f}%" if q is not None else f"ERR {err}"
                print(f"    s{s} rep{rep + 1}: {t:.0f}s {tag}", flush=True)
        rows.append(row)

    with capsys.disabled():
        _print_report(rows, baselines)
        if skipped:
            print(f"\nskipped jobs: {len(skipped)}")
            for s in skipped:
                print(f"  - {s}")
