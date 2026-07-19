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
    """Test that filter falls back to HTML text (not a hard-fail) when pdf_text is None."""
    optimized = OptimizedResume(
        html="<div>Test</div>",
        source_checksum=source_resume.checksum,
        pdf_text=None,
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    assert not result.passed
    assert "No PDF text available" not in result.issues


@pytest.mark.asyncio
async def test_keyword_matcher_html_only_no_pdf_text(source_resume, job_posting):
    # Editor /validate path: html set, pdf_text is None. Should still score, not hard-fail.
    optimized = OptimizedResume(
        html="<div>Backend Engineer with Python Django PostgreSQL REST API experience</div>",
        source_checksum=source_resume.checksum,
        pdf_text=None,
    )

    matcher = KeywordMatcher()
    result = await matcher.evaluate(optimized, job_posting, source_resume)

    assert result.passed
    assert result.score >= matcher.threshold
    assert "No PDF text available" not in result.issues


@pytest.mark.asyncio
async def test_keyword_matcher_no_content_at_all(source_resume, job_posting):
    optimized = OptimizedResume(
        html=None, source_checksum=source_resume.checksum, pdf_text=None
    )
    result = await KeywordMatcher().evaluate(optimized, job_posting, source_resume)
    assert not result.passed


@pytest.mark.asyncio
async def test_keyword_matcher_symbol_keywords_match():
    from hr_breaker.filters.keyword_matcher import check_keywords

    job = JobPosting(
        title="Systems Engineer",
        company="Acme",
        requirements=["C++", "C#", ".NET"],
        keywords=["c++", "c#", ".net"],
    )
    resume_text = "Built low-latency services in C++ and C#, plus tooling on .NET."

    result = check_keywords(resume_text, job)

    assert "c++" not in result.missing_keywords
    assert "c#" not in result.missing_keywords
    assert ".net" not in result.missing_keywords


@pytest.mark.asyncio
async def test_keyword_matcher_alnum_still_whole_word():
    from hr_breaker.filters.keyword_matcher import check_keywords

    job = JobPosting(title="Dev", company="Acme", requirements=[], keywords=["java"])
    # "javascript" must NOT satisfy the "java" keyword.
    result = check_keywords("Expert in JavaScript frameworks.", job)
    assert "java" in result.missing_keywords


@pytest.mark.asyncio
async def test_keyword_matcher_cyrillic_whole_word():
    from hr_breaker.filters.keyword_matcher import check_keywords

    # requirements includes a Latin token so the TF-IDF vectorizer doesn't raise
    # on an all-Cyrillic job_text (empty vocabulary) before keywords are added.
    job = JobPosting(
        title="Разработчик", company="Acme", requirements=["Python"], keywords=["питон"]
    )
    # "питоны" (plural) must NOT satisfy the "питон" keyword; bare "питон" must.
    assert "питон" in check_keywords("Знаю питоны и джаву", job).missing_keywords
    assert "питон" not in check_keywords("Знаю питон и джаву", job).missing_keywords


def test_filter_registry():
    """Test that filters are registered."""
    names = FilterRegistry.names()
    assert "KeywordMatcher" in names


def test_filter_threshold_property():
    """Test threshold property on filters."""
    matcher = KeywordMatcher()
    assert matcher.threshold == 0.25


@pytest.mark.asyncio
async def test_vector_matcher_score_is_raw_cosine(monkeypatch):
    import numpy as np
    from hr_breaker.filters import vector_similarity_matcher as vsm

    class FakeModel:
        def encode(self, texts):
            # Nearly-orthogonal vectors -> cosine ~0.0, must be BELOW 0.4 threshold.
            return np.array([[1.0, 0.0], [0.0, 1.0]])

    monkeypatch.setattr(
        vsm.VectorSimilarityMatcher, "_get_model", lambda self: FakeModel()
    )

    job = JobPosting(title="Chef", company="Acme", description="Cook food", requirements=[])
    optimized = OptimizedResume(
        html="<div>x</div>", source_checksum="c", pdf_text="Quantum physics research"
    )
    result = await vsm.VectorSimilarityMatcher().evaluate(optimized, job, ResumeSource(content="x"))

    assert result.score < 0.05          # raw cosine, not (sim+1)/2 == 0.5
    assert not result.passed            # 0.0 < 0.4 threshold


@pytest.mark.asyncio
async def test_vector_matcher_no_literal_none(monkeypatch):
    import numpy as np
    from hr_breaker.filters import vector_similarity_matcher as vsm

    captured = {}

    class FakeModel:
        def encode(self, texts):
            captured["job_text"] = texts[1]
            return np.array([[1.0, 0.0], [1.0, 0.0]])

    monkeypatch.setattr(
        vsm.VectorSimilarityMatcher, "_get_model", lambda self: FakeModel()
    )

    # JobPosting.description is a non-Optional `str` field, so normal validated
    # construction rejects `description=None` outright (ValidationError) before
    # the matcher ever runs. model_construct bypasses validation to reproduce
    # the None value the guard is meant to handle.
    job = JobPosting.model_construct(
        title="Chef", company="Acme", description=None, requirements=[]
    )
    optimized = OptimizedResume(html="<div>x</div>", source_checksum="c", pdf_text="Cook")
    await vsm.VectorSimilarityMatcher().evaluate(optimized, job, ResumeSource(content="x"))

    assert "None" not in captured["job_text"]


@pytest.mark.asyncio
async def test_content_length_reuses_existing_pdf_bytes(monkeypatch, job_posting):
    from hr_breaker.filters import content_length as content_length_mod
    from hr_breaker.filters.content_length import ContentLengthChecker

    def boom():
        raise AssertionError("renderer must not be constructed when pdf_bytes exists")

    # Patch the name as bound in content_length.py (it's `from ... import get_renderer`,
    # so patching hr_breaker.services.renderer.get_renderer wouldn't touch this reference).
    monkeypatch.setattr(content_length_mod, "get_renderer", boom)

    # Minimal 1-page PDF produced once via a real render in a fixture would be ideal;
    # here we render a tiny doc directly to get valid bytes.
    from hr_breaker.services.renderer import HTMLRenderer
    pdf = HTMLRenderer().render("<h1>Test</h1><p>Short resume.</p>").pdf_bytes

    optimized = OptimizedResume(
        html="<h1>Test</h1><p>Short resume.</p>",
        source_checksum="c",
        pdf_bytes=pdf,
    )
    result = await ContentLengthChecker().evaluate(optimized, job_posting, ResumeSource(content="x"))
    assert result.passed


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
