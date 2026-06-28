"""Tests for orchestration module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from hr_breaker.models import (
    FilterResult,
    JobPosting,
    OptimizedResume,
    ResumeSource,
    ValidationResult,
)
from hr_breaker.models.audit import AuditScore
from hr_breaker.orchestration import optimize_for_job, run_filters


def _audit(**overrides):
    base = dict(
        ats_compatibility="ATS-Ready", recruiter_scan="Strong",
        bullet_quality="Strong", seniority_calibration="Aligned",
        keyword_coverage="Strong", structure="Strong",
        concern_management="Strong", consistency="Strong",
        overall="Strong", top_fixes=[],
    )
    base.update(overrides)
    return AuditScore(**base)


def _validation(passed: bool):
    return ValidationResult(results=[
        FilterResult(filter_name="F", passed=passed, score=1.0 if passed else 0.0,
                     threshold=0.7)
    ])


@pytest.fixture
def source_resume():
    return ResumeSource(content="Test resume content")


@pytest.fixture
def job_posting():
    return JobPosting(
        title="Engineer",
        company="Test Corp",
        requirements=["Python"],
        keywords=["python"],
    )


@pytest.fixture
def optimized_resume(source_resume):
    return OptimizedResume(
        html="<div>Test</div>",
        source_checksum=source_resume.checksum,
        pdf_text="Test resume text",
    )


class TestRunFiltersParallel:
    @pytest.mark.asyncio
    async def test_parallel_handles_filter_exception(
        self, source_resume, job_posting, optimized_resume
    ):
        """If one filter raises, others should still return results."""
        good_result = FilterResult(
            filter_name="GoodFilter",
            passed=True,
            score=0.9,
            threshold=0.5,
            issues=[],
            suggestions=[],
        )

        class GoodFilter:
            name = "GoodFilter"
            priority = 1

            async def evaluate(self, *args):
                return good_result

        class BadFilter:
            name = "BadFilter"
            priority = 2

            async def evaluate(self, *args):
                raise RuntimeError("Filter crashed!")

        # Mock registry to return our test filters
        with patch("hr_breaker.orchestration.FilterRegistry.all") as mock_all:
            mock_all.return_value = [GoodFilter, BadFilter]

            # Should NOT raise, should return partial results
            validation = await run_filters(
                optimized_resume, job_posting, source_resume, parallel=True
            )

            # Should have results from working filter + error for crashed one
            assert len(validation.results) >= 1
            # The validation should not have passed (one filter crashed)
            # At minimum, the good result should be present
            good_results = [r for r in validation.results if r.filter_name == "GoodFilter"]
            assert len(good_results) == 1
            assert good_results[0].passed


@pytest.mark.asyncio
async def test_optimize_for_job_uses_v1_by_default(source_resume, job_posting):
    """When OPTIMIZER_VERSION is not set (v1), uses optimize_resume."""
    from hr_breaker.orchestration import optimize_for_job
    from hr_breaker.config import get_settings

    mock_optimized = OptimizedResume(
        html="<div>v1 result</div>",
        source_checksum=source_resume.checksum,
        pdf_text="v1 text",
        pdf_bytes=b"%PDF-1.4",
    )

    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v1"}):
        get_settings.cache_clear()
        with patch("hr_breaker.orchestration.HTMLRenderer"), \
             patch("hr_breaker.orchestration.optimize_resume", new_callable=AsyncMock, return_value=mock_optimized) as mock_v1, \
             patch("hr_breaker.orchestration.optimize_resume_v2", new_callable=AsyncMock) as mock_v2, \
             patch("hr_breaker.orchestration._render_and_extract", return_value=mock_optimized), \
             patch("hr_breaker.orchestration.run_filters", new_callable=AsyncMock) as mock_filters:
            from hr_breaker.models import ValidationResult
            mock_filters.return_value = ValidationResult(results=[])
            await optimize_for_job(source=source_resume, job=job_posting, max_iterations=1)
            mock_v1.assert_called_once()
            mock_v2.assert_not_called()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_optimize_for_job_uses_v2_when_flag_set(source_resume, job_posting):
    """When OPTIMIZER_VERSION=v2, uses optimize_resume_v2."""
    from hr_breaker.orchestration import optimize_for_job
    from hr_breaker.config import get_settings
    from hr_breaker.models.audit import AuditScore

    audit = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Strong",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Strong",
        top_fixes=["fix1", "fix2", "fix3"],
    )
    mock_optimized = OptimizedResume(
        html="<div>v2 result</div>",
        source_checksum=source_resume.checksum,
        pdf_text="v2 text",
        pdf_bytes=b"%PDF-1.4",
        audit=audit,
    )

    with patch.dict("os.environ", {"OPTIMIZER_VERSION": "v2"}):
        get_settings.cache_clear()
        with patch("hr_breaker.orchestration.HTMLRenderer"), \
             patch("hr_breaker.orchestration.optimize_resume", new_callable=AsyncMock) as mock_v1, \
             patch("hr_breaker.orchestration.optimize_resume_v2", new_callable=AsyncMock, return_value=mock_optimized) as mock_v2, \
             patch("hr_breaker.orchestration._render_and_extract", return_value=mock_optimized), \
             patch("hr_breaker.orchestration.run_filters", new_callable=AsyncMock) as mock_filters:
            from hr_breaker.models import ValidationResult
            mock_filters.return_value = ValidationResult(results=[])
            result_optimized, _, _ = await optimize_for_job(source=source_resume, job=job_posting, max_iterations=1)
            mock_v2.assert_called_once()
            mock_v1.assert_not_called()
            assert result_optimized.audit is not None
    get_settings.cache_clear()


class TestConvergence:
    @pytest.mark.asyncio
    async def test_stops_on_success_target(self, source_resume, job_posting):
        """Filters pass AND no dim below Moderate -> stop after iteration 1."""
        optimized = OptimizedResume(html="<div/>", source_checksum=source_resume.checksum,
                                    pdf_text="text")
        optimize_mock = AsyncMock(return_value=optimized)
        with patch("hr_breaker.orchestration.optimize_resume", new=optimize_mock), \
             patch("hr_breaker.orchestration.optimize_resume_v2", new=optimize_mock), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(True))), \
             patch("hr_breaker.orchestration.audit_resume", new=AsyncMock(return_value=_audit())) as m_audit:
            await optimize_for_job(source_resume, job=job_posting, max_iterations=3)
        # baseline audit (1) + exactly one in-loop audit
        assert m_audit.await_count == 2

    @pytest.mark.asyncio
    async def test_stops_on_plateau_patience_1(self, source_resume, job_posting):
        """Filters never pass; audit plateaus -> stop via patience. optimize
        runs exactly 3 times (iter0 sets best, iter1 flat=no_improve 1,
        iter2 flat=no_improve 2 > patience 1 -> break), not the full 5."""
        optimized = OptimizedResume(html="<div/>", source_checksum=source_resume.checksum,
                                    pdf_text="text")
        flat_audit = _audit(bullet_quality="Weak")  # Weak => success target never met
        optimize_mock = AsyncMock(return_value=optimized)
        with patch("hr_breaker.orchestration.optimize_resume", new=optimize_mock), \
             patch("hr_breaker.orchestration.optimize_resume_v2", new=optimize_mock), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(False))), \
             patch("hr_breaker.orchestration.audit_resume", new=AsyncMock(return_value=flat_audit)):
            await optimize_for_job(source_resume, job=job_posting, max_iterations=5)
        assert optimize_mock.await_count == 3

    @pytest.mark.asyncio
    async def test_returns_best_not_last(self, source_resume, job_posting):
        """If a later iteration regresses, the earlier better one is returned."""
        good = OptimizedResume(html="<good/>", source_checksum=source_resume.checksum,
                               pdf_text="good")
        bad = OptimizedResume(html="<bad/>", source_checksum=source_resume.checksum,
                              pdf_text="bad")
        optimize_mock = AsyncMock(side_effect=[good, bad, bad])
        audit_mock = AsyncMock(side_effect=[
            _audit(bullet_quality="Weak"),                                   # iter0: high sum, Weak blocks success
            _audit(bullet_quality="Weak", structure="Weak", recruiter_scan="Weak"),  # iter1: worse
            _audit(bullet_quality="Weak", structure="Weak", recruiter_scan="Weak"),
        ])
        with patch("hr_breaker.orchestration.optimize_resume", new=optimize_mock), \
             patch("hr_breaker.orchestration.optimize_resume_v2", new=optimize_mock), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(False))), \
             patch("hr_breaker.orchestration.audit_resume", new=audit_mock):
            result, _, _ = await optimize_for_job(source_resume, job=job_posting, max_iterations=3)
        assert result.html == "<good/>"

    @pytest.mark.asyncio
    async def test_uses_fewer_iterations_than_cap(self, source_resume, job_posting):
        """Speed guarantee: when audit quality improves then plateaus, the loop
        stops well before the iteration cap instead of grinding through it.

        structure stays Weak throughout so the success target never fires and
        filters never pass — the only thing that can stop the loop early is
        convergence. The baseline audit (before the loop) consumes the first
        side_effect entry; the in-loop ordinal-sum then climbs 10 -> 12 -> 14
        and flattens:
          iter0 q=10 (best), iter1 q=12 (best), iter2 q=14 (best),
          iter3 q=14 (no_improve=1), iter4 q=14 (no_improve=2 > patience) -> break.
        So 5 iterations run against a cap of 8. If convergence regressed and the
        loop ran to the cap, await_count would be 8 and this test would fail.
        """
        optimized = OptimizedResume(html="<div/>", source_checksum=source_resume.checksum,
                                    pdf_text="text")
        improving_then_flat = [
            _audit(structure="Weak"),  # baseline audit (guidance only, not counted)
            _audit(structure="Weak", recruiter_scan="Weak", keyword_coverage="Weak"),      # iter0 q=10
            _audit(structure="Weak", recruiter_scan="Moderate", keyword_coverage="Moderate"),  # iter1 q=12
            _audit(structure="Weak"),  # iter2 q=14
            _audit(structure="Weak"),  # iter3 q=14 (plateau)
            _audit(structure="Weak"),  # iter4 q=14 (plateau -> break)
        ]
        optimize_mock = AsyncMock(return_value=optimized)
        cap = 8
        with patch("hr_breaker.orchestration.optimize_resume", new=optimize_mock), \
             patch("hr_breaker.orchestration.optimize_resume_v2", new=optimize_mock), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(False))), \
             patch("hr_breaker.orchestration.audit_resume", new=AsyncMock(side_effect=improving_then_flat)):
            await optimize_for_job(source_resume, job=job_posting, max_iterations=cap)
        assert optimize_mock.await_count == 5
        assert optimize_mock.await_count < cap
