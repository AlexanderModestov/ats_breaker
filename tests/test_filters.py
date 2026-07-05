import pytest

from hr_breaker.filters import FilterRegistry, KeywordMatcher
from hr_breaker.models import JobPosting, OptimizedResume, ResumeSource


@pytest.fixture
def source_resume():
    return ResumeSource(
        content="""
John Doe
Experience with Python and Django
Built REST APIs serving 1000+ users
5 years experience in software development
"""
    )


@pytest.fixture
def job_posting():
    return JobPosting(
        title="Backend Engineer",
        company="Acme",
        requirements=["Python", "Django", "PostgreSQL"],
        keywords=["python", "django", "postgresql", "rest", "api"],
    )


@pytest.mark.asyncio
async def test_keyword_matcher_full_match(source_resume, job_posting):
    optimized = OptimizedResume(
        html="<div>Backend Engineer with Python Django PostgreSQL REST API experience</div>",
        source_checksum=source_resume.checksum,
        pdf_text="Backend Engineer with Python Django PostgreSQL REST API experience",
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    # TF-IDF scores are weighted - all explicit keywords match, so should pass
    assert result.passed
    assert result.score >= matcher.threshold
    assert result.threshold == 0.25


@pytest.mark.asyncio
async def test_keyword_matcher_partial_match(source_resume, job_posting):
    optimized = OptimizedResume(
        html="<div>Python experience</div>",
        source_checksum=source_resume.checksum,
        pdf_text="Python experience",
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    assert result.score < 1.0
    assert len(result.issues) > 0


@pytest.mark.asyncio
async def test_keyword_matcher_no_pdf_text(source_resume, job_posting):
    """Test that filter fails gracefully when pdf_text is None."""
    optimized = OptimizedResume(
        html="<div>Test</div>",
        source_checksum=source_resume.checksum,
        pdf_text=None,
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    assert not result.passed
    assert "No PDF text available" in result.issues[0]


def test_filter_registry():
    """Test that filters are registered."""
    names = FilterRegistry.names()
    assert "KeywordMatcher" in names


def test_filter_threshold_property():
    """Test threshold property on filters."""
    matcher = KeywordMatcher()
    assert matcher.threshold == 0.25


def test_filter_priorities_unique():
    """All filter priorities should be unique for deterministic execution order."""
    filters = FilterRegistry.all()
    priorities = [f.priority for f in filters]
    names = [f.name for f in filters]

    # Find duplicates
    seen = {}
    for name, priority in zip(names, priorities):
        if priority in seen:
            pytest.fail(
                f"Duplicate priority {priority}: {seen[priority]} and {name}"
            )
        seen[priority] = name
