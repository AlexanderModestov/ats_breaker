"""Tests for job_parser grounding helpers and merge logic."""

import pytest

from hr_breaker.agents.job_parser import (
    COMPANY_NOT_SPECIFIED,
    _normalize,
    _strip_corp_suffix,
    _is_grounded,
)


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
