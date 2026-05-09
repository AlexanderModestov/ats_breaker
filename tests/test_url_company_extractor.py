"""Tests for URL-based company extraction."""

import pytest

from hr_breaker.agents.url_company_extractor import extract_company_from_url


@pytest.mark.parametrize(
    "url,expected",
    [
        # Tier 1: subdomain == company
        ("https://podcastle.bamboohr.com/careers/56", "podcastle"),
        ("https://acme.workable.com/jobs/123", "acme"),
        ("https://foo.recruitee.com/o/bar", "foo"),
        ("https://co.teamtailor.com/jobs/9", "co"),
        ("https://startup.breezy.hr/p/abc", "startup"),
        ("https://corp.myworkdayjobs.com/en-US/External", "corp"),
        # Tier 2: first path segment == company
        ("https://boards.greenhouse.io/podcastle/jobs/123", "podcastle"),
        ("https://jobs.lever.co/acme/abcdef", "acme"),
        ("https://jobs.ashbyhq.com/foo/bar-baz", "foo"),
        ("https://apply.workable.com/podcastle/j/ABC", "podcastle"),
        # Tier 2 must beat Tier 1 for hybrid hosts
        ("https://apply.workable.com/some-co/j/X", "some-co"),
        # Reserved subdomains rejected
        ("https://www.bamboohr.com/", None),
        ("https://jobs.bamboohr.com/", None),
        # Bare host (no company subdomain) rejected
        ("https://bamboohr.com/", None),
        # Tier 2 with empty path rejected
        ("https://boards.greenhouse.io/", None),
        # Tier 2 with reserved first segment rejected
        ("https://boards.greenhouse.io/jobs/123", None),
        # Unknown hosts rejected
        ("https://www.linkedin.com/jobs/view/123", None),
        ("https://t.me/rfoundersjobs/639", None),
        ("https://hh.ru/vacancy/123", None),
        # Malformed / empty inputs
        ("", None),
        ("not a url", None),
        ("ftp://podcastle.bamboohr.com/", "podcastle"),  # scheme-agnostic; host is what matters
    ],
)
def test_extract_company_from_url(url, expected):
    assert extract_company_from_url(url) == expected
