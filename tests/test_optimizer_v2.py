"""Tests for optimizer v2 agent."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hr_breaker.models import ResumeSource, OptimizedResume, JobPosting
from hr_breaker.models.audit import AuditScore
from hr_breaker.models.iteration import IterationContext


@pytest.fixture
def source():
    return ResumeSource(content="Python developer with 5 years experience")


@pytest.fixture
def job():
    return JobPosting(
        title="Senior Python Developer",
        company="Acme",
        requirements=["Python", "FastAPI"],
        keywords=["python", "fastapi", "rest"],
    )


@pytest.fixture
def context(source):
    return IterationContext(
        iteration=0,
        original_resume=source.content,
    )


def test_optimize_resume_v2_returns_optimized_resume_with_audit(source, job, context):
    """optimize_resume_v2 returns OptimizedResume with audit populated."""
    from hr_breaker.agents.optimizer_v2 import OptimizerV2Result
    from hr_breaker.agents import optimize_resume_v2

    mock_audit = AuditScore(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Moderate",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="NA",
        consistency="Strong",
        overall="Strong",
        top_fixes=["Add metrics to bullets", "Tighten summary", "Reorder skills"],
    )
    mock_result = OptimizerV2Result(
        html="<header><h1>Test</h1></header>",
        changes=["Rewrote bullets using XYZ formula"],
        audit=mock_audit,
    )

    mock_agent_run = AsyncMock()
    mock_agent_run.return_value.output = mock_result

    with patch("hr_breaker.agents.optimizer_v2.get_optimizer_v2_agent") as mock_get_agent:
        mock_agent = MagicMock()
        mock_agent.run = mock_agent_run
        mock_get_agent.return_value = mock_agent

        result = asyncio.run(optimize_resume_v2(source, job, context))

    assert isinstance(result, OptimizedResume)
    assert result.html == "<header><h1>Test</h1></header>"
    assert result.audit is not None
    assert result.audit.overall == "Strong"
    assert result.audit.ats_compatibility == "ATS-Ready"
    assert result.iteration == 0
