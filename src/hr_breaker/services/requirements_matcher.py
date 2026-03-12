"""Service to match job requirements against resume HTML content."""

from __future__ import annotations

import re

from hr_breaker.models import JobPosting, RequirementItem


def _strip_html(html: str) -> str:
    """Remove HTML tags from *html* and return plain text."""
    return re.sub(r"<[^>]+>", " ", html)


def _significant_words(text: str) -> list[str]:
    """Extract words with 3+ characters from *text*."""
    return [w for w in re.findall(r"[A-Za-z0-9+#.\-]+", text) if len(w) >= 3]


def match_requirements(job: JobPosting, html: str) -> list[RequirementItem]:
    """Match job requirements and keywords against resume *html*.

    Returns a list of :class:`RequirementItem` indicating which requirements
    and keywords are covered by the resume.
    """
    plain = _strip_html(html).lower()

    items: list[RequirementItem] = []

    # --- requirements ---
    all_req_text = " ".join(job.requirements).lower()

    for idx, req in enumerate(job.requirements):
        words = _significant_words(req)
        if not words:
            covered = False
        else:
            matched = sum(1 for w in words if w.lower() in plain)
            covered = matched / len(words) >= 0.5
        items.append(RequirementItem(id=f"req_{idx}", text=req, covered=covered))

    # --- keywords not already in requirements text ---
    kw_idx = 0
    for kw in job.keywords:
        if kw.lower() in all_req_text:
            continue
        covered = kw.lower() in plain
        items.append(RequirementItem(id=f"kw_{kw_idx}", text=kw, covered=covered))
        kw_idx += 1

    return items
