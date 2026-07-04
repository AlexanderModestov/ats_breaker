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
    Skips trajectories whose endpoints lack an audit. A dimension whose value is
    "NA" at either endpoint is skipped for that trajectory, mirroring the
    NA-exclusion in models/audit.py (ordinal_sum / no_dim_below_moderate)."""
    out = {}
    for dim in _DIMENSIONS:
        firsts, lasts = [], []
        for t in trajs:
            if not t.points or t.points[0].audit is None or t.points[-1].audit is None:
                continue
            first_val = getattr(t.points[0].audit, dim)
            last_val = getattr(t.points[-1].audit, dim)
            if first_val == "NA" or last_val == "NA":
                continue
            firsts.append(_LEVEL[first_val])
            lasts.append(_LEVEL[last_val])
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
