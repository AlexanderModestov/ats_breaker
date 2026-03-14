"""End-to-end test for the resume editor flow."""

from hr_breaker.models import JobPosting
from hr_breaker.models.editor import ResumePatch
from hr_breaker.services.requirements_matcher import match_requirements
from hr_breaker.services.patch_applier import apply_patches


def test_full_edit_flow():
    """Simulate: check requirements -> apply patch -> re-check."""
    job = JobPosting(
        title="Python Developer",
        company="Acme",
        location="Remote",
        requirements=[
            "5+ years Python",
            "Docker experience",
            "REST API design",
        ],
        responsibilities=["Build services"],
        keywords=["Python", "Docker", "REST", "FastAPI"],
        description="Python dev role",
        raw_text="Full text",
    )

    html = '<div id="summary"><p>Java developer with 10 years experience</p></div>'

    # Step 1: Check requirements — most should be uncovered
    reqs = match_requirements(job, html)
    uncovered_before = [r for r in reqs if not r.covered]
    assert len(uncovered_before) >= 2

    # Step 2: Apply patches manually (simulating LLM output)
    patches = [
        ResumePatch(
            selector="#summary p",
            action="replace",
            html="<p>Python developer with 5 years of experience in Docker containers and REST API design using FastAPI framework.</p>",
        ),
    ]
    updated = apply_patches(html, patches)
    assert "Python" in updated
    assert "Docker" in updated

    # Step 3: Re-check — more should be covered now
    reqs_after = match_requirements(job, updated)
    uncovered_after = [r for r in reqs_after if not r.covered]
    assert len(uncovered_after) < len(uncovered_before)
