import pytest


# Name extraction tests hit the live LLM; gated like the other benchmark tests
# (skipped unless run with `-m benchmark`, see conftest.py).
pytestmark = pytest.mark.benchmark


async def test_extract_name_with_name_command():
    from hr_breaker.agents import extract_name

    latex = r"\name{John}{Doe}"
    first, last = await extract_name(latex)
    assert first == "John"
    assert last == "Doe"


async def test_extract_name_with_huge():
    from hr_breaker.agents import extract_name

    latex = r"{\Huge John Doe}"
    first, last = await extract_name(latex)
    assert first == "John"
    assert last == "Doe"


async def test_extract_name_fallback():
    from hr_breaker.agents import extract_name

    latex = """
\\documentclass{article}
\\begin{document}
John Smith
\\end{document}
"""
    first, last = await extract_name(latex)
    assert first == "John"
    assert last == "Smith"


async def test_extract_name_nested_formatting():
    """Test that nested LaTeX formatting is handled correctly."""
    from hr_breaker.agents import extract_name

    latex = r"\name{\normalsize{Boris Tseitlin}}"
    first, last = await extract_name(latex)
    assert first == "Boris"
    assert last == "Tseitlin"


async def test_extract_name_not_found():
    from hr_breaker.agents import extract_name

    latex = r"\documentclass{article}"
    first, last = await extract_name(latex)
    assert first is None
    assert last is None
