from typing import Literal
from pydantic import BaseModel


class AuditScore(BaseModel):
    """Audit scores for the 8-dimension resume optimization."""

    ats_compatibility: Literal["ATS-Ready", "ATS-Risky", "ATS-Broken"]
    recruiter_scan: Literal["Strong", "Moderate", "Weak"]
    bullet_quality: Literal["Strong", "Moderate", "Weak"]
    seniority_calibration: Literal["Aligned", "Mismatched"]
    keyword_coverage: Literal["Strong", "Moderate", "Weak"]
    structure: Literal["Strong", "Moderate", "Weak"]
    concern_management: Literal["Strong", "Moderate", "Weak", "NA"]
    consistency: Literal["Strong", "Moderate", "Weak"]
    overall: Literal["Strong", "Needs Work", "Weak"]
    top_fixes: list[str]


# Ordinal mapping for convergence scoring. Strong/Moderate/Weak map identically
# across all dimensions that use them; ATS and seniority have their own labels.
# `NA` (concern_management only) is excluded from both helpers.
_LEVEL = {
    "Strong": 2, "Moderate": 1, "Weak": 0,
    "ATS-Ready": 2, "ATS-Risky": 1, "ATS-Broken": 0,
    "Aligned": 2, "Mismatched": 0,
}

_DIMENSIONS = (
    "ats_compatibility",
    "recruiter_scan",
    "bullet_quality",
    "seniority_calibration",
    "keyword_coverage",
    "structure",
    "concern_management",
    "consistency",
)


def ordinal_sum(audit: AuditScore) -> int:
    """Sum each applicable dimension's ordinal level (0/1/2). Range 0..16
    (0..14 when concern_management is NA). `overall` is not counted."""
    total = 0
    for dim in _DIMENSIONS:
        value = getattr(audit, dim)
        if value == "NA":
            continue
        total += _LEVEL[value]
    return total


def no_dim_below_moderate(audit: AuditScore) -> bool:
    """True when every applicable dimension is Moderate-level or better
    (ATS-Risky counts as Moderate; ATS-Broken and Mismatched fail). NA skipped."""
    for dim in _DIMENSIONS:
        value = getattr(audit, dim)
        if value == "NA":
            continue
        if _LEVEL[value] < 1:
            return False
    return True
