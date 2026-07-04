# Iteration-Cap Comparison Experiment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a benchmark that runs one cap=5 optimization K times per job, then *derives* the 2/3/4/5 cap outcomes exactly from each run's per-iteration trajectory — validating whether raising the cap changes anything now that convergence stops early.

**Architecture:** Split into pure logic (unit-tested, no LLM) and an LLM-gated harness. `tests/caps_experiment.py` holds dataclasses + pure derivation/aggregation/report functions. `tests/test_caps_experiment.py` unit-tests them with synthetic trajectories (runs in normal CI). `tests/test_caps_comparison.py` is the `@pytest.mark.benchmark` harness: a **synchronous** collector passed as `on_iteration` stashes each iteration's HTML/filters/time, then after the run we re-audit each stashed HTML to fill quality and build a `RunTrajectory`. Report is rendered by a pure string function so it's testable.

**Tech Stack:** Python 3, pytest + pytest-asyncio, dataclasses, `statistics`. Reuses `tests/test_optimizer_comparison.py` helpers and `hr_breaker.orchestration.optimize_for_job`.

**Design doc:** `docs/plans/2026-07-04-caps-comparison-experiment-design.md`

---

## Background facts (verified against current code)

- Sibling harness `tests/test_steps_comparison.py` runs each step count separately; we instead run once at cap=5 and derive. It imports from `tests/test_optimizer_comparison.py`: `RESUME_PATH`, `POSITIONS_PATH`, `_bootstrap_vertex`, `_ingest_job`, `_slug`, `_split_positions`, `_with_retry`, `audit_resume_avg`. Reuse the same set.
- `audit_resume_avg(html, job, n=..., model=...)` is async and returns `(quality_pct: float, audit: AuditScore)` (see `test_steps_comparison.py:100,147`).
- `optimize_for_job(source, job=..., max_iterations=..., on_iteration=..., parallel=True)` returns `(optimized, validation, job)`. The `on_iteration(i, optimized, validation)` callback is **synchronous**, fires once per iteration AFTER filters run, with `optimized.html` and `optimized.pdf_text` populated (`orchestration.py`). Callback fire count == iterations actually run.
- The loop returns the BEST iteration by audit ordinal-sum, not the last. The cap only appears as `range(max_iterations)` — it truncates but does not change per-iteration behavior before it binds. This is what makes deriving lower caps from one cap=5 run exact.
- `AuditScore` (`src/hr_breaker/models/audit.py:5-17`) has 8 categorical dimensions. `_DIMENSIONS` and the Strong/Moderate/Weak→2/1/0 mapping live there (module-private `_LEVEL`, `_DIMENSIONS`).
- `benchmark` marker is already used by the sibling files; no config change needed.
- `.gitignore` has a bare `tests` rule; new test files must be committed with `git add -f` (existing tests are tracked the same way).

---

## Task 1: Trajectory data structures + cap derivation

**Files:**
- Create: `tests/caps_experiment.py`
- Test: `tests/test_caps_experiment.py`

**Step 1: Write the failing tests**

Create `tests/test_caps_experiment.py`:

```python
"""Unit tests for the pure caps-experiment derivation logic (no LLM)."""

from tests.caps_experiment import IterPoint, RunTrajectory, CapOutcome, cap_result


def _traj(best_qualities, stop=None):
    """Build a trajectory from a list of best-so-far qualities (one per iteration)."""
    points = [
        IterPoint(iteration=i, quality=q, best_quality=q,
                  filters_passed=0, filters_total=1, cum_seconds=float(i + 1), audit=None)
        for i, q in enumerate(best_qualities)
    ]
    return RunTrajectory(job_slug="job", rep=0, points=points)


def test_stop_iteration_is_point_count():
    assert _traj([50.0, 60.0]).stop_iteration == 2


def test_cap_below_stop_truncates_to_best_so_far():
    # ran 3 iters (best-so-far 50->60->70); cap=2 returns best of first 2 = 60
    t = _traj([50.0, 60.0, 70.0])
    out = cap_result(t, 2)
    assert out.iterations_used == 2
    assert out.quality == 60.0
    assert out.cap_bound is True          # cap 2 < stop 3 -> it truncated
    assert out.seconds == 2.0


def test_cap_at_or_above_stop_returns_full_run():
    t = _traj([50.0, 60.0, 70.0])
    for n in (3, 4, 5):
        out = cap_result(t, n)
        assert out.iterations_used == 3
        assert out.quality == 70.0
        assert out.cap_bound is False     # cap never truncated
        assert out.seconds == 3.0


def test_immediate_success_makes_all_caps_identical():
    t = _traj([82.0])                     # converged at iteration 1
    assert t.stop_iteration == 1
    for n in (2, 3, 4, 5):
        out = cap_result(t, n)
        assert out.iterations_used == 1
        assert out.quality == 82.0
        assert out.cap_bound is False


def test_empty_trajectory_raises():
    import pytest
    with pytest.raises(ValueError):
        cap_result(RunTrajectory(job_slug="j", rep=0, points=[]), 3)
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_caps_experiment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.caps_experiment'`.

**Step 3: Implement the data structures + `cap_result`**

Create `tests/caps_experiment.py`:

```python
"""Pure logic for the iteration-cap comparison experiment.

No LLM, no I/O — trajectory derivation, aggregation, and report rendering.
Imported by both the unit tests and the benchmark harness.
"""

from dataclasses import dataclass


@dataclass
class IterPoint:
    """One iteration of a single optimize run."""
    iteration: int          # 0-based
    quality: float          # this iteration's audit quality %
    best_quality: float     # running max quality up to & incl. this iteration
    filters_passed: int
    filters_total: int
    cum_seconds: float      # wall-time from run start through this iteration
    audit: object = None    # AuditScore | None (kept for per-dimension deltas)


@dataclass
class RunTrajectory:
    """All iterations of one cap=MAX run (one repetition of one job)."""
    job_slug: str
    rep: int
    points: list            # list[IterPoint]

    @property
    def stop_iteration(self) -> int:
        """How many iterations actually ran (where convergence stopped)."""
        return len(self.points)


@dataclass
class CapOutcome:
    """What a run capped at `cap` would have returned, derived from a trajectory."""
    cap: int
    quality: float
    iterations_used: int
    cap_bound: bool         # did the cap truncate the run (cap < stop)?
    seconds: float


def cap_result(traj: RunTrajectory, n: int) -> CapOutcome:
    """Derive the cap=n outcome from a (>= n)-length trajectory.

    The loop returns the best-so-far iteration, so a truncation at k iterations
    returns points[k-1].best_quality. Exact because the cap only truncates.
    """
    if not traj.points:
        raise ValueError("cannot derive cap result from an empty trajectory")
    k = min(n, traj.stop_iteration)
    pt = traj.points[k - 1]
    return CapOutcome(
        cap=n,
        quality=pt.best_quality,
        iterations_used=k,
        cap_bound=n < traj.stop_iteration,
        seconds=pt.cum_seconds,
    )
```

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_caps_experiment.py -v`
Expected: PASS (5 tests).

**Step 5: Commit**

```bash
git add -f tests/caps_experiment.py tests/test_caps_experiment.py
git commit -m "feat(experiment): caps trajectory model + derivation"
```

---

## Task 2: Aggregation + report rendering

**Files:**
- Modify: `tests/caps_experiment.py`
- Test: `tests/test_caps_experiment.py`

**Step 1: Write the failing tests**

Append to `tests/test_caps_experiment.py`:

```python
from tests.caps_experiment import (
    summarize_cap, stop_distribution, dimension_deltas, render_caps_report,
)


def test_summarize_cap_means_and_bound_pct():
    # two reps: one converges at 2 (best 70), one at 1 (best 82)
    trajs = [_traj([50.0, 70.0]), _traj([82.0])]
    s = summarize_cap(trajs, 3)          # cap 3 >= both stops -> never bound
    assert s.cap == 3
    assert s.quality_mean == 76.0        # (70 + 82) / 2
    assert s.iters_mean == 1.5           # (2 + 1) / 2
    assert s.cap_bound_pct == 0.0
    s2 = summarize_cap(trajs, 1)         # cap 1 truncates the 2-iter run only
    assert s2.cap_bound_pct == 50.0
    assert s2.quality_mean == 66.0       # (50 + 82) / 2


def test_stop_distribution_counts():
    trajs = [_traj([1.0]), _traj([1.0, 2.0]), _traj([1.0, 2.0])]
    assert stop_distribution(trajs) == {1: 1, 2: 2}


def test_dimension_deltas_first_vs_last():
    from hr_breaker.models.audit import AuditScore

    def mk(recruiter):
        return AuditScore(
            ats_compatibility="ATS-Ready", recruiter_scan=recruiter,
            bullet_quality="Strong", seniority_calibration="Aligned",
            keyword_coverage="Strong", structure="Strong",
            concern_management="Strong", consistency="Strong",
            overall="Strong", top_fixes=[],
        )
    p0 = IterPoint(0, 50.0, 50.0, 0, 1, 1.0, audit=mk("Weak"))     # recruiter 0
    p1 = IterPoint(1, 60.0, 60.0, 0, 1, 2.0, audit=mk("Strong"))   # recruiter 2
    trajs = [RunTrajectory("j", 0, [p0, p1])]
    deltas = dimension_deltas(trajs)
    assert deltas["recruiter_scan"] == (0.0, 2.0)   # (mean first, mean last)
    assert deltas["structure"] == (2.0, 2.0)        # unchanged


def test_render_caps_report_contains_blocks():
    trajs = [_traj([50.0, 70.0]), _traj([82.0])]
    text = render_caps_report(trajs, caps=(2, 3, 4, 5))
    assert "CAP" in text and "CAP_BOUND" in text
    assert "Stopped at iteration" in text
    # every cap appears as a row
    for n in (2, 3, 4, 5):
        assert f" {n} " in text or f"{n}\t" in text
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_caps_experiment.py -k "summarize or distribution or deltas or render" -v`
Expected: FAIL with `ImportError: cannot import name 'summarize_cap'`.

**Step 3: Implement aggregation + report**

Append to `tests/caps_experiment.py`:

```python
from statistics import mean, pstdev

# Ordinal levels for per-dimension deltas. Mirrors _LEVEL in models/audit.py
# (kept local so the experiment doesn't depend on a private symbol).
_LEVEL = {
    "Strong": 2, "Moderate": 1, "Weak": 0,
    "ATS-Ready": 2, "ATS-Risky": 1, "ATS-Broken": 0,
    "Aligned": 2, "Mismatched": 0,
}
_DIMENSIONS = (
    "ats_compatibility", "recruiter_scan", "bullet_quality",
    "seniority_calibration", "keyword_coverage", "structure",
    "concern_management", "consistency",
)


@dataclass
class CapSummary:
    cap: int
    quality_mean: float
    quality_sd: float
    iters_mean: float
    cap_bound_pct: float
    time_mean: float


def summarize_cap(trajs: list, n: int) -> CapSummary:
    outs = [cap_result(t, n) for t in trajs]
    qs = [o.quality for o in outs]
    return CapSummary(
        cap=n,
        quality_mean=mean(qs),
        quality_sd=pstdev(qs) if len(qs) > 1 else 0.0,
        iters_mean=mean(o.iterations_used for o in outs),
        cap_bound_pct=100.0 * sum(o.cap_bound for o in outs) / len(outs),
        time_mean=mean(o.seconds for o in outs),
    )


def stop_distribution(trajs: list) -> dict:
    dist: dict[int, int] = {}
    for t in trajs:
        dist[t.stop_iteration] = dist.get(t.stop_iteration, 0) + 1
    return dist


def dimension_deltas(trajs: list) -> dict:
    """Mean ordinal (0..2) at iteration 0 vs final iteration, per dimension.
    Skips trajectories whose endpoints lack an audit. NA dimensions contribute 0."""
    def lvl(audit, dim):
        return _LEVEL.get(getattr(audit, dim), 0)
    out = {}
    for dim in _DIMENSIONS:
        firsts, lasts = [], []
        for t in trajs:
            if not t.points or t.points[0].audit is None or t.points[-1].audit is None:
                continue
            firsts.append(lvl(t.points[0].audit, dim))
            lasts.append(lvl(t.points[-1].audit, dim))
        if firsts:
            out[dim] = (mean(firsts), mean(lasts))
    return out


def render_caps_report(trajs: list, caps=(2, 3, 4, 5)) -> str:
    lines = []
    lines.append("=== ITERATION-CAP COMPARISON ===")
    lines.append(f"runs: {len(trajs)}  (quality bands are mean +/- sd, indicative only)")
    lines.append("")
    lines.append(f"{'CAP':>3}  {'QUALITY%':>14}  {'ITERS':>6}  {'CAP_BOUND%':>10}  {'TIME_s':>7}")
    for n in caps:
        s = summarize_cap(trajs, n)
        q = f"{s.quality_mean:.1f} +/- {s.quality_sd:.1f}"
        lines.append(f"{n:>3}  {q:>14}  {s.iters_mean:>6.1f}  {s.cap_bound_pct:>9.0f}%  {s.time_mean:>7.1f}")
    lines.append("")
    dist = stop_distribution(trajs)
    parts = "   ".join(f"{k}: {'#' * v} ({v})" for k, v in sorted(dist.items()))
    lines.append(f"Stopped at iteration:  {parts}")
    lines.append("")
    deltas = dimension_deltas(trajs)
    if deltas:
        lines.append("Per-dimension ordinal (iter0 -> final, 0..2):")
        for dim, (a, b) in deltas.items():
            arrow = "up" if b > a else ("--" if b == a else "DOWN")
            lines.append(f"  {dim:<22} {a:.2f} -> {b:.2f}  {arrow}")
    return "\n".join(lines)
```

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_caps_experiment.py -v`
Expected: PASS (all Task 1 + Task 2 tests, ~9 total).

**Step 5: Commit**

```bash
git add -f tests/caps_experiment.py tests/test_caps_experiment.py
git commit -m "feat(experiment): caps aggregation + report rendering"
```

---

## Task 3: The benchmark harness

**Files:**
- Create: `tests/test_caps_comparison.py`
- Test: (no unit test — LLM-gated benchmark; verified by collection + skip behavior. The pure logic it calls is already covered by Task 1–2.)

**Step 1: Implement the harness**

Create `tests/test_caps_comparison.py`:

```python
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
    """One cap=MAX_CAP run; collect iterations, then re-audit each to build points."""
    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    t0 = time.perf_counter()
    raw, on_iter = _make_collector(t0)
    with contextlib.redirect_stdout(io.StringIO()):
        await _with_retry(lambda: optimize_for_job(
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
```

**Step 2: Verify it collects and skips cleanly (no LLM spent)**

Run: `uv run pytest tests/test_caps_comparison.py -v`
Expected: the test is collected and reported as SKIPPED (benchmark marker is deselected by default OR inputs/Vertex not present). It must NOT error on import or collection.

Run: `uv run pytest tests/test_caps_comparison.py --collect-only -q`
Expected: shows `test_caps_comparison` with no import errors.

**Step 3: Commit**

```bash
git add -f tests/test_caps_comparison.py
git commit -m "feat(experiment): iteration-cap comparison benchmark harness"
```

**Step 4 (optional, manual — spends real LLM budget): run the experiment**

Only when you want real numbers, with Vertex creds + inputs present:

Run: `uv run pytest tests/test_caps_comparison.py -s -m benchmark`
Expected: prints the three report blocks. Interpret: if `CAP_BOUND%` is ~0 at cap≥3, higher caps are dead weight; the stop distribution shows where to set the default cap; per-dimension deltas show which dimensions iterations fail to move.

---

## Final verification

```bash
uv run pytest tests/test_caps_experiment.py -v          # pure logic, all pass
uv run pytest tests/test_caps_comparison.py --collect-only -q   # imports cleanly
```

Do NOT run the full suite expecting green — there are pre-existing unrelated
failures (`test_utils` live-LLM, `test_config` v1/v2 stale test). Report, don't
fix (out of scope).

## Out of scope (do not touch)

- `orchestration.py`, `on_iteration`, optimizer/auditor, and all production code —
  the experiment is read-only against the pipeline.
- Extending the `on_iteration` signature — we deliberately keep it and re-audit
  post-run instead.
- PDF saving per cap (the sibling steps harness does it; not needed for this
  validation — YAGNI).
- Registering the `benchmark` marker (already configured for the sibling files).
