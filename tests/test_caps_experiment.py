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
