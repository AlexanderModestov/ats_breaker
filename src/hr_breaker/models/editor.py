"""Pydantic models for the resume editor feature."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ResumePatch(BaseModel):
    """CSS-selector-based patch for modifying resume HTML."""

    selector: str
    """CSS selector targeting the element to modify (e.g. ``#skills-list``)."""

    action: Literal["replace", "append", "prepend", "remove"]
    """Operation to perform on the matched element."""

    html: str | None = None
    """New HTML content. Required for replace/append/prepend; None for remove."""


class EditResult(BaseModel):
    """Output returned by the resume-editor LLM agent."""

    patches: list[ResumePatch]
    """Ordered list of patches to apply to the resume HTML."""

    reasoning: str
    """LLM explanation of why these changes were made."""


class RequirementItem(BaseModel):
    """A single job requirement and whether the resume covers it."""

    id: str
    """Unique identifier for the requirement."""

    text: str
    """Human-readable requirement text."""

    covered: bool
    """Whether the current resume adequately addresses this requirement."""
