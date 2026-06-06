"""Tests for job_parser grounding helpers and merge logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hr_breaker.agents.job_parser import (
    COMPANY_NOT_SPECIFIED,
    _normalize,
    _strip_corp_suffix,
    _is_grounded,
    parse_job_posting,
)
from hr_breaker.models import JobPosting
from hr_breaker.models import JobHints


class TestNormalize:
    def test_lowercases(self):
        assert _normalize("Hello World") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize("a   b\tc\nd") == "a b c d"

    def test_replaces_separators_with_space(self):
        # middle dot, em-dash, en-dash, comma, semicolon, slash, pipe
        assert _normalize("a · b — c – d, e; f/g|h") == "a b c d e f g h"

    def test_keeps_hyphen_minus(self):
        assert _normalize("Coca-Cola") == "coca-cola"

    def test_unicode_nfc(self):
        # decomposed "é" (e + combining acute) → composed "é"
        assert _normalize("Café") == _normalize("Café")


class TestStripCorpSuffix:
    @pytest.mark.parametrize(
        "input_,expected",
        [
            ("Podcastle Inc.", "Podcastle"),
            ("Podcastle Inc", "Podcastle"),
            ("Acme LLC", "Acme"),
            ("Acme L.L.C.", "Acme"),
            ("Foo Ltd.", "Foo"),
            ("Foo Limited", "Foo"),
            ("Bar Corp", "Bar"),
            ("Bar Corporation", "Bar"),
            ("Baz Co.", "Baz"),
            ("Baz Company", "Baz"),
            ("Acme GmbH", "Acme"),
            ("Acme S.A.", "Acme"),
            ("Acme B.V.", "Acme"),
            ("Acme Pte Ltd", "Acme"),
            ("Volkswagen Group", "Volkswagen"),
            ("Hertz Holdings", "Hertz"),
            ("ООО Ромашка", "ООО Ромашка"),  # leading suffix not stripped (anchored to end)
            ("Ромашка ООО", "Ромашка"),
            ("Acme, Inc., LLC", "Acme"),  # cascading
            ("Plain Name", "Plain Name"),  # no-op
            ("", ""),
        ],
    )
    def test_strips_trailing_corp_suffix(self, input_, expected):
        assert _strip_corp_suffix(input_) == expected


class TestIsGrounded:
    def test_empty_value_is_grounded(self):
        assert _is_grounded("", "any text") is True

    def test_unknown_short_circuits(self):
        assert _is_grounded("Unknown", "") is True
        assert _is_grounded(COMPANY_NOT_SPECIFIED, "") is True

    def test_substring_match_passes(self):
        assert _is_grounded("Podcastle", "Working at Podcastle is great") is True

    def test_all_words_match_passes(self):
        assert _is_grounded(
            "Senior Backend Engineer",
            "We seek a Senior Engineer with Backend skills",
        ) is True

    def test_separator_difference_passes_with_normalization(self):
        assert _is_grounded(
            "Senior Engineer, Backend",
            "Senior Engineer · Backend at Acme",
        ) is True

    def test_unrelated_value_fails(self):
        assert _is_grounded("Microsoft", "Working at Apple is great") is False

    def test_company_suffix_stripped_when_is_company(self):
        assert _is_grounded(
            "Podcastle Inc.",
            "We are Podcastle, a great place",
            is_company=True,
        ) is True

    def test_company_suffix_not_stripped_for_title(self):
        # Title with trailing "Co" should not be stripped — but also the words rule
        # would still find "Senior Engineer" in text; this tests the gate, not behavior.
        # Using a clearly-failing case to prove the suffix isn't stripped:
        assert _is_grounded(
            "Solo Inc.",
            "Solo is hiring",
            is_company=False,
        ) is False  # "Inc." not in text, suffix not stripped → fails

    def test_cyrillic_suffix_company(self):
        assert _is_grounded(
            "Ромашка ООО",
            "Работаем в компании Ромашка уже 10 лет",
            is_company=True,
        ) is True


def _mock_agent_returning(job: JobPosting):
    """Build a mock pydantic-ai Agent whose .run() returns the given JobPosting."""
    fake_result = MagicMock()
    fake_result.output = job
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=fake_result)
    return mock_agent


@pytest.mark.asyncio
class TestParseJobPostingMerge:
    async def test_no_url_keeps_llm_value_when_grounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
        text = "Podcastle is hiring a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(text)
        assert job.company == "Podcastle Inc."

    async def test_no_url_replaces_with_not_specified_when_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Podcastle is hiring a Backend Eng."  # Microsoft not in text
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(text)
        assert job.company == COMPANY_NOT_SPECIFIED

    async def test_url_fills_in_when_llm_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # neither company appears
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "podcastle"

    async def test_url_keeps_llm_canonical_when_agreeing(self):
        llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
        text = "Podcastle is hiring a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "Podcastle Inc."  # LLM canonical wins on agreement

    async def test_url_overrides_on_conflict(self):
        llm_job = JobPosting(title="Backend Eng", company="Acme Corp")
        text = "Acme Corp posted: Backend Eng."  # LLM grounded but URL says podcastle
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "podcastle"

    async def test_url_with_unknown_host_is_noop(self):
        llm_job = JobPosting(title="Backend Eng", company="Acme Corp")
        text = "Acme Corp posted: Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(text, url="https://t.me/rfoundersjobs/639")
        assert job.company == "Acme Corp"

    async def test_returns_empty_needs_review_when_all_grounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Podcastle Inc.")
        text = "Podcastle is hiring a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(text)
        assert needs_review == []

    async def test_needs_review_contains_company_when_not_specified(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Acme is hiring a Backend Eng."  # company not grounded, no URL
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(text)
        assert job.company == COMPANY_NOT_SPECIFIED
        assert "company" in needs_review

    async def test_needs_review_omits_company_when_url_filled(self):
        # LLM ungrounded but URL provided a fallback → final company is fine
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56"
            )
        assert job.company == "podcastle"
        assert "company" not in needs_review

    async def test_needs_review_contains_title_when_ungrounded(self):
        llm_job = JobPosting(title="Fabricated Title", company="Podcastle Inc.")
        text = "Podcastle is hiring."  # title not in text
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(text)
        assert "title" in needs_review

    async def test_jsonld_company_beats_url(self):
        # JSON-LD company is authoritative even over a known URL slug
        llm_job = JobPosting(title="Backend Eng", company="Wrong Co")
        text = "Wrong Co is hiring a Backend Eng."  # LLM grounded, but JSON-LD wins
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text,
                url="https://podcastle.bamboohr.com/careers/56",
                hints=JobHints(company="Acme", company_source="json-ld"),
            )
        assert job.company == "Acme"

    async def test_meta_company_ranks_below_url(self):
        # og:site_name often = the job board; URL slug must win over a meta hint
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # LLM ungrounded
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text,
                url="https://podcastle.bamboohr.com/careers/56",
                hints=JobHints(company="BambooHR", company_source="meta"),
            )
        assert job.company == "podcastle"

    async def test_meta_company_used_when_no_url_and_llm_ungrounded(self):
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."  # LLM ungrounded, no URL slug
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(company="Acme", company_source="meta")
            )
        assert job.company == "Acme"
        assert "company" not in needs_review

    async def test_jsonld_title_overrides_llm(self):
        llm_job = JobPosting(title="Vague Title", company="Acme")
        text = "Acme is hiring."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(title="Senior Backend Engineer", title_source="json-ld")
            )
        assert job.title == "Senior Backend Engineer"
        assert "title" not in needs_review

    async def test_meta_title_only_used_when_llm_ungrounded(self):
        # grounded LLM title beats a meta-sourced hint (avoids "… | Board" junk)
        llm_job = JobPosting(title="Backend Eng", company="Acme")
        text = "Acme is hiring a Backend Eng."  # LLM grounded
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, hints=JobHints(title="Backend Eng - Acme | JobBoard", title_source="meta")
            )
        assert job.title == "Backend Eng"

    async def test_hint_location_used(self):
        llm_job = JobPosting(title="Eng", company="Acme", location="")
        text = "Acme is hiring an Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(
                text, hints=JobHints(location="Berlin, DE")
            )
        assert job.location == "Berlin, DE"
        assert "location" not in needs_review

    async def test_ungrounded_llm_location_kept_conservatively(self):
        # No hint, LLM location not grounded → kept as-is, never blanked or flagged
        llm_job = JobPosting(title="Eng", company="Acme", location="San Francisco")
        text = "Acme is hiring an Eng in SF."  # "San Francisco" not literally present
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, needs_review = await parse_job_posting(text)
        assert job.location == "San Francisco"
        assert "location" not in needs_review

    async def test_no_hints_reproduces_old_company_behavior(self):
        # hints=None path must match the pre-existing URL-fallback behavior
        llm_job = JobPosting(title="Backend Eng", company="Microsoft")
        text = "Looking for a Backend Eng."
        with patch(
            "hr_breaker.agents.job_parser.get_job_parser_agent",
            return_value=_mock_agent_returning(llm_job),
        ):
            job, _ = await parse_job_posting(
                text, url="https://podcastle.bamboohr.com/careers/56", hints=None
            )
        assert job.company == "podcastle"
