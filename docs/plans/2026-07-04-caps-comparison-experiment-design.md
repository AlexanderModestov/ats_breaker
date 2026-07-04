# Iteration-Cap Comparison Experiment — Design

**Date:** 2026-07-04
**Status:** Approved design, pending implementation plan

## Goal

Validate whether raising the optimization iteration **cap** (2 / 3 / 4 / 5)
changes the outcome, now that the convergence work makes `max_iterations` a hard
cap that the loop stops short of when audit quality plateaus (patience 1) or the
success target is met. Secondary goal: surface *where* the optimization process
can be improved.

## Background

Since the convergence change, `max_iterations` is a cap, not a target. The loop
(`orchestration.py` `optimize_for_job`) stops early on:
- **success target** — filters pass AND `no_dim_below_moderate(audit)`, or
- **patience** — no ordinal-sum improvement for `PATIENCE` (=1) iterations,

and returns the **best** iteration by audit ordinal-sum, not the last.

Existing infra to reuse (`tests/test_steps_comparison.py`,
`tests/test_optimizer_comparison.py`):
- `quality_score(audit) -> 0..100%` (AuditScore → ordinal points).
- `audit_resume_avg(html, job, n)` — averages N audits.
- `_ingest_job()` / positions split — production-mirroring job ingestion.
- Inputs: `output/Alexander Modestov.pdf`, `positions.txt`.
- `on_iteration(i, optimized, validation)` callback.

## Key insight — one cap=5 run derives all caps

The cap only appears as `range(max_iterations)`; it **truncates** the loop but
does not change its behavior before it binds, and the convergence checks are
cap-independent. Therefore a single cap=5 run stops at whatever iteration
convergence fires, and its per-iteration best-so-far trajectory **exactly**
determines what cap=2/3/4 would have returned. We never run the lower caps
directly — ~4× cheaper, and we still get variance bands from repetition.

## Experiment flow

New file `tests/test_caps_comparison.py` (`@pytest.mark.benchmark`, gated on real
Vertex creds + local inputs, modeled on `test_steps_comparison.py`).

For each job, run `optimize_for_job(..., max_iterations=5)` **K=3 times**. In the
`on_iteration` callback (production interface untouched):
1. Record filters-passed and cumulative wall-time.
2. Re-audit `optimized.pdf_text` → `AuditScore` → quality% (reuse
   `audit_resume_avg` + `quality_score`).
3. Track best-so-far quality (mirror the loop's return-best behavior).

Actual stop point = callback fire count (independent of the re-audit).

### Why re-audit rather than extend the callback

`on_iteration` is used by CLI and API. Re-auditing in the harness keeps that
interface untouched (surgical-changes rule). The extra audit call is acceptable
for a one-off benchmark. "Actual iterations used" comes from the callback fire
count, so it does not depend on the re-audited score matching the loop's
internal audit.

## Data structures

```python
@dataclass
class IterPoint:
    iteration: int          # 0-based
    quality: float          # this iteration's audit quality %
    best_quality: float     # running max up to & incl. this iteration
    filters_passed: int
    filters_total: int
    cum_seconds: float

@dataclass
class RunTrajectory:
    job_slug: str
    rep: int
    points: list[IterPoint]
    stop_iteration: int     # len(points) — where convergence stopped
```

### Cap derivation (pure, no LLM)

```python
def cap_result(traj, n):
    k = min(n, traj.stop_iteration)
    pt = traj.points[k - 1]
    return CapOutcome(
        quality=pt.best_quality,               # loop returns best, not last
        iterations_used=k,
        cap_bound=n < traj.stop_iteration,     # did the cap truncate?
        seconds=pt.cum_seconds,
    )
```

`cap_bound=False` means the cap ≥ the convergence stop, so raising it changed
nothing. If `cap_bound` is `False` for cap=3 across all runs, caps 4–5 are
provably dead weight.

Edge case: a run that stops at iteration 1 (immediate success target) makes
every cap identical — recorded as `stop_iteration=1`.

## Report output

Printed to stdout, tee'd to `output/caps_comparison_run.log`.

**Block 1 — Per-cap summary (headline):**
```
CAP  QUALITY%(mean±sd)  ITERS_USED(mean)  CAP_BOUND%   TIME_s(mean)
 2      78.4 ± 4.1           2.0             67%          14.2
 3      82.1 ± 3.8           2.7             11%          19.8
 4      82.3 ± 3.9           2.8              0%          20.3
 5      82.3 ± 3.9           2.8              0%          20.3
```
Quality flattening + `CAP_BOUND% → 0` is the validation.

**Block 2 — Convergence stop distribution:**
```
Stopped at iteration:  1: ▓▓ (2)   2: ▓▓▓▓▓ (5)   3: ▓▓ (2)   4+: (0)
```
Empirical basis for choosing the default cap.

**Block 3 — Per-dimension deltas (improvement lens):**
For each of the 8 AuditScore dimensions, average ordinal score at iteration 0 vs
final iteration. Reveals which dimensions iterations actually move — raw material
for the "how to improve" goal.

## Config

```python
MAX_CAP = 5
REPS = 3
AUDIT_SAMPLES = 2
OPTIMIZER_VERSION = "v2"      # pinned via env, like test_steps_comparison
MODEL = "gemini-2.5-flash"    # pinned for cost/speed
```
No CLI flags (YAGNI). Cost: 3 jobs × 3 reps = 9 optimization runs.
Command: `uv run pytest tests/test_caps_comparison.py -s -m benchmark`.

## Determinism caveats (stated in the report header)

- Optimizer and auditor are stochastic; quality bands (mean ± sd over K=3) are
  indicative, not statistically powerful. The **robust conclusions are
  `CAP_BOUND%` and the stop distribution** — near-deterministic structural facts
  (did the cap truncate?), not noisy quality deltas.
- Re-auditing may differ slightly from the loop's internal convergence audit; we
  do not rely on them matching.

## Actionable outputs

- Block 2 → whether the default cap should drop below 3.
- Block 3 → which dimensions iterations fail to move → prompt/filter gaps to
  target next.

## Scope

**New:** `tests/test_caps_comparison.py` + this doc.
**Unchanged:** `orchestration.py`, `on_iteration`, the optimizer/auditor, and all
production code. The experiment is read-only against the pipeline.
