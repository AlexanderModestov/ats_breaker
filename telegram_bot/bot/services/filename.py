"""Resume filename formatter."""

import re

_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')


def _clean(value: str | None) -> str:
    return _FORBIDDEN.sub("", value or "").strip()


def format_resume_filename(run: dict) -> str:
    """Build a speaking PDF filename from an optimization run dict.

    Shape: ``{First Last} - {Company} - {Title}.pdf`` — any missing or
    sanitization-emptied piece is dropped. Falls back to ``resume.pdf``
    when no piece survives.
    """
    first = _clean(run.get("first_name"))
    last = _clean(run.get("last_name"))
    job = run.get("job_parsed") or {}
    company = _clean(job.get("company"))
    title = _clean(job.get("title"))

    name = " ".join(p for p in (first, last) if p)
    parts = [p for p in (name, company, title) if p]
    return f"{' - '.join(parts) if parts else 'resume'}.pdf"
