"""Tests for the requirements matcher service."""

from hr_breaker.models import JobPosting, RequirementItem
from hr_breaker.services.requirements_matcher import match_requirements


def _make_job(**kwargs) -> JobPosting:
    defaults = {"title": "Software Engineer", "company": "Acme"}
    defaults.update(kwargs)
    return JobPosting(**defaults)


def test_match_requirements_all_covered():
    job = _make_job(
        requirements=["Python programming", "REST API development"],
        keywords=["Python", "REST"],
    )
    html = "<div>Experienced in Python programming and REST API development</div>"

    items = match_requirements(job, html)

    req_items = [i for i in items if i.id.startswith("req_")]
    assert len(req_items) == 2
    assert all(i.covered for i in req_items)


def test_match_requirements_partial():
    job = _make_job(
        requirements=["Python programming", "Kubernetes orchestration"],
        keywords=[],
    )
    html = "<p>Strong Python programming skills</p>"

    items = match_requirements(job, html)

    by_id = {i.id: i for i in items}
    assert by_id["req_0"].covered is True
    assert by_id["req_1"].covered is False


def test_match_requirements_case_insensitive():
    job = _make_job(
        requirements=["PYTHON Programming"],
        keywords=["DOCKER"],
    )
    html = "<span>python programming and docker experience</span>"

    items = match_requirements(job, html)

    assert all(i.covered for i in items)


def test_keywords_not_in_requirements_added():
    job = _make_job(
        requirements=["Python programming"],
        keywords=["Python", "Docker", "Kubernetes"],
    )
    # "Python" appears in requirements text, so only Docker and Kubernetes
    # should be added as separate keyword items.
    html = "<div>Python programming, Docker containers</div>"

    items = match_requirements(job, html)

    kw_items = [i for i in items if i.id.startswith("kw_")]
    # "Python" is already in a requirement, so excluded; Docker & Kubernetes remain
    assert len(kw_items) == 2
    kw_by_text = {i.text: i for i in kw_items}
    assert kw_by_text["Docker"].covered is True
    assert kw_by_text["Kubernetes"].covered is False
