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
