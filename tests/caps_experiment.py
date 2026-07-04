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
