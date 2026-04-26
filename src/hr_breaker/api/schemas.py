"""Pydantic request/response models for the API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# User schemas
class UserProfile(BaseModel):
    """User profile data."""

    id: str
    email: str
    name: str | None = None
    theme: str = "minimal"
    default_cv_id: str | None = None
    created_at: datetime


class UserProfileUpdate(BaseModel):
    """Update user profile."""

    name: str | None = None
    theme: str | None = None
    default_cv_id: str | None = None


class AuthVerifyRequest(BaseModel):
    """Request to verify auth token."""

    access_token: str


class AuthVerifyResponse(BaseModel):
    """Response from auth verification."""

    valid: bool
    user_id: str | None = None
    email: str | None = None


# CV schemas
class CVResponse(BaseModel):
    """CV data returned from API."""

    id: str
    name: str
    original_filename: str
    content_text: str | None = None
    created_at: datetime


class CVListResponse(BaseModel):
    """List of CVs."""

    cvs: list[CVResponse]


class CVDeleteResponse(BaseModel):
    """Response from CV deletion."""

    success: bool
    message: str


# Optimization schemas
class OptimizeRequest(BaseModel):
    """Request to start optimization."""

    cv_id: str
    job_input: str = Field(..., description="Job posting URL or text")
    max_iterations: int = Field(default=5, ge=1, le=10)
    parallel: bool = Field(default=True, description="Run filters in parallel")


class OptimizationStatus(BaseModel):
    """Optimization run status."""

    id: str
    status: str = Field(..., description="pending|parse_job|generate|validate|refine|complete|failed")
    current_step: str | None = None
    iterations: int = 0
    job_parsed: dict[str, Any] | None = None
    job_url: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    feedback: list[dict[str, Any]] | None = None
    result_html: str | None = None
    error: str | None = None
    timing: dict[str, float] | None = Field(None, description="Timing breakdown in seconds")
    created_at: datetime


class OptimizationStartResponse(BaseModel):
    """Response from starting optimization."""

    run_id: str
    status: str


class OptimizationSummary(BaseModel):
    """Summary of an optimization run for listing."""

    id: str
    status: str
    job_title: str | None = None
    job_company: str | None = None
    job_url: str | None = None
    created_at: datetime


class OptimizationListResponse(BaseModel):
    """List of optimization runs."""

    runs: list[OptimizationSummary]


# Filter result schemas
class FilterResultResponse(BaseModel):
    """Single filter result."""

    filter_name: str
    passed: bool
    score: float
    threshold: float
    issues: list[str]
    suggestions: list[str]


class ValidationResultResponse(BaseModel):
    """Validation result with all filters."""

    passed: bool
    results: list[FilterResultResponse]


# Health check
class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"


class CoachChatRequest(BaseModel):
    """Request to send a message to the coach."""

    session_id: str | None = None
    optimization_run_id: str
    message: str


class CoachSessionResponse(BaseModel):
    """Coach session info."""

    id: str
    optimization_run_id: str
    created_at: str
    updated_at: str


class CoachMessageResponse(BaseModel):
    """Coach message for display."""

    role: str
    content: str


class StorybankEntryRequest(BaseModel):
    """Request to create/update a storybank entry."""

    title: str
    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""
    tags: list[str] = []
    rating: int | None = None


class StorybankEntryResponse(BaseModel):
    """Storybank entry."""

    id: str
    title: str
    situation: str
    task: str
    action: str
    result: str
    tags: list[str]
    rating: int | None
    created_at: str
    updated_at: str
