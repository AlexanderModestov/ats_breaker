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
