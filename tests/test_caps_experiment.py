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


def test_dimension_deltas_skips_na_dimension():
    from hr_breaker.models.audit import AuditScore

    def mk(recruiter, concern):
        return AuditScore(
            ats_compatibility="ATS-Ready", recruiter_scan=recruiter,
            bullet_quality="Strong", seniority_calibration="Aligned",
            keyword_coverage="Strong", structure="Strong",
            concern_management=concern, consistency="Strong",
            overall="Strong", top_fixes=[],
        )
    p0 = IterPoint(0, 50.0, 50.0, 0, 1, 1.0, audit=mk("Weak", "NA"))
    p1 = IterPoint(1, 60.0, 60.0, 0, 1, 2.0, audit=mk("Strong", "NA"))
    trajs = [RunTrajectory("j", 0, [p0, p1])]
    deltas = dimension_deltas(trajs)
    assert "concern_management" not in deltas   # NA excluded, not treated as 0
    assert deltas["recruiter_scan"] == (0.0, 2.0)


def test_render_caps_report_contains_blocks():
    trajs = [_traj([50.0, 70.0]), _traj([82.0])]
    text = render_caps_report(trajs, caps=(2, 3, 4, 5))
    assert "CAP" in text and "CAP_BOUND" in text
    assert "Stopped at iteration" in text
    # every cap appears as a row
    for n in (2, 3, 4, 5):
        assert f" {n} " in text or f"{n}\t" in text
