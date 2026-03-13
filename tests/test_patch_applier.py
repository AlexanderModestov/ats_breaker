"""Tests for the patch applier service."""

from hr_breaker.models.editor import ResumePatch
from hr_breaker.services.patch_applier import apply_patches

SAMPLE_HTML = """
<div id="summary"><p>Software engineer</p></div>
<div id="skills-list"><ul><li>Java</li></ul></div>
<div id="experience-item-0"><ul><li>Built APIs</li></ul></div>
"""


def test_append_patch():
    patches = [
        ResumePatch(selector="#skills-list ul", action="append", html="<li>Python</li>"),
    ]
    result = apply_patches(SAMPLE_HTML, patches)
    assert "<li>Java</li>" in result
    assert "<li>Python</li>" in result
    # Python should come after Java
    assert result.index("<li>Java</li>") < result.index("<li>Python</li>")


def test_replace_patch():
    patches = [
        ResumePatch(selector="#summary p", action="replace", html="<p>Senior engineer</p>"),
    ]
    result = apply_patches(SAMPLE_HTML, patches)
    assert "Senior engineer" in result
    assert "Software engineer" not in result


def test_remove_patch():
    patches = [
        ResumePatch(selector="#experience-item-0", action="remove", html=None),
    ]
    result = apply_patches(SAMPLE_HTML, patches)
    assert "experience-item-0" not in result
    assert "Built APIs" not in result
    # Other elements should remain
    assert "skills-list" in result


def test_prepend_patch():
    patches = [
        ResumePatch(selector="#skills-list ul", action="prepend", html="<li>Leadership</li>"),
    ]
    result = apply_patches(SAMPLE_HTML, patches)
    assert "<li>Leadership</li>" in result
    assert "<li>Java</li>" in result
    # Leadership should come before Java
    assert result.index("<li>Leadership</li>") < result.index("<li>Java</li>")


def test_missing_selector_skipped():
    patches = [
        ResumePatch(selector="#nonexistent", action="remove", html=None),
    ]
    result = apply_patches(SAMPLE_HTML, patches)
    # HTML should be unchanged (modulo whitespace normalization by parser)
    assert "summary" in result
    assert "skills-list" in result
    assert "experience-item-0" in result
