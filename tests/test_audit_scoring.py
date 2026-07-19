"""Tests for AuditScore ordinal mapping used by convergence."""

from hr_breaker.models.audit import AuditScore, ordinal_sum, no_dim_below_moderate


def _audit(**overrides):
    """An all-Strong baseline AuditScore, with per-dimension overrides."""
    base = dict(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Strong",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="Strong",
        consistency="Strong",
        overall="Strong",
        top_fixes=[],
    )
    base.update(overrides)
    return AuditScore(**base)


def test_auditor_agent_is_cached():
    from hr_breaker.agents.auditor import get_auditor_agent
    assert get_auditor_agent() is get_auditor_agent()
    assert get_auditor_agent(model="gemini-2.5-pro") is get_auditor_agent(model="gemini-2.5-pro")


def test_ordinal_sum_all_top_is_16():
    assert ordinal_sum(_audit()) == 16


def test_ordinal_sum_all_bottom_is_0():
    assert ordinal_sum(
        _audit(
            ats_compatibility="ATS-Broken",
            recruiter_scan="Weak",
            bullet_quality="Weak",
            seniority_calibration="Mismatched",
            keyword_coverage="Weak",
            structure="Weak",
            concern_management="Weak",
            consistency="Weak",
        )
    ) == 0


def test_na_concern_management_is_excluded():
    # 7 dims at Strong/Ready/Aligned (2 each) = 14, concern_management NA skipped
    assert ordinal_sum(_audit(concern_management="NA")) == 14


def test_ordinal_sum_mixed():
    # Risky=1, Moderate=1, Mismatched=0, rest Strong/Ready/Aligned=2
    a = _audit(
        ats_compatibility="ATS-Risky",   # 1
        recruiter_scan="Moderate",        # 1
        seniority_calibration="Mismatched",  # 0
    )
    # 1 + 1 + 2 + 0 + 2 + 2 + 2 + 2 = 12
    assert ordinal_sum(a) == 12


def test_no_dim_below_moderate_true_with_risky_and_moderate():
    # ATS-Risky and Moderate both count as Moderate-level (>= 1) → True
    assert no_dim_below_moderate(
        _audit(ats_compatibility="ATS-Risky", recruiter_scan="Moderate")
    ) is True


def test_no_dim_below_moderate_false_on_weak():
    assert no_dim_below_moderate(_audit(bullet_quality="Weak")) is False


def test_no_dim_below_moderate_false_on_ats_broken():
    assert no_dim_below_moderate(_audit(ats_compatibility="ATS-Broken")) is False


def test_no_dim_below_moderate_false_on_mismatched_seniority():
    assert no_dim_below_moderate(_audit(seniority_calibration="Mismatched")) is False


def test_no_dim_below_moderate_ignores_na():
    assert no_dim_below_moderate(_audit(concern_management="NA")) is True


def test_looks_like_html_distinguishes_generics_from_markup():
    from hr_breaker.agents.auditor import _looks_like_html
    assert _looks_like_html("<div>Resume</div>") is True
    assert _looks_like_html("<p>Experience</p>") is True
    assert _looks_like_html("Implemented Cache<T> generics in C++") is False
    assert _looks_like_html("Skills: math < stats") is False
    # Uppercase / mixed-case real HTML must still be detected (reachable via .html CV uploads).
    assert _looks_like_html("<DIV>Header</DIV>") is True
    assert _looks_like_html("<P>Experience</P>") is True
    # Single-letter generics must NOT be treated as HTML regardless of case.
    assert _looks_like_html("Map<K, V> and Cache<T>") is False
