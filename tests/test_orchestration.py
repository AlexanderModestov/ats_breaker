"""Tests for orchestration module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from hr_breaker.models import (
    FilterResult,
    JobPosting,
    OptimizedResume,
    ResumeSource,
)
from hr_breaker.orchestration import run_filters


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
