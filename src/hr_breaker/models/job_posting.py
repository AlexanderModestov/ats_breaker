from pydantic import BaseModel, Field


class JobPosting(BaseModel):
    """Structured job posting data."""

    title: str
    company: str
    location: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    description: str = ""
    raw_text: str = ""


class JobHints(BaseModel):
    """Structured fields harvested deterministically from page markup.

    Populated by scrapers from schema.org JobPosting JSON-LD or OpenGraph
    meta tags. Each field is None when not found — never invented.
    """

    title: str | None = None
    company: str | None = None
    location: str | None = None
    company_source: str | None = None  # "json-ld" | "meta" — company precedence vs URL slug
    title_source: str | None = None    # "json-ld" | "meta" — json-ld title authoritative; meta is fallback
