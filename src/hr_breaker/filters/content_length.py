"""Content length checker - runs first to fail fast on oversized content."""

import asyncio

import fitz

from hr_breaker.config import get_settings, logger
from hr_breaker.filters.base import BaseFilter
from hr_breaker.filters.registry import FilterRegistry
from hr_breaker.models import FilterResult, JobPosting, OptimizedResume, ResumeSource
from hr_breaker.services.length_estimator import estimate_content_length
from hr_breaker.services.renderer import get_renderer, RenderError


def check_page2_overflow(pdf_bytes: bytes) -> str | None:
    """Check if page 2 is mostly empty (content overflow).

    Returns error message if overflow detected, None otherwise.
    """
    settings = get_settings()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if len(doc) < 2:
            return None
        page2_text = doc[1].get_text().strip()
    if len(page2_text) > 0 and len(page2_text) < settings.resume_page2_overflow_chars:
        logger.debug(
            f"check_page2_overflow: page 2 len {len(page2_text)} - overflow from page 1"
        )
        return f"Page 2 has only {len(page2_text)} chars - content overflow from page 1"
    return None


@FilterRegistry.register
class ContentLengthChecker(BaseFilter):
    """Pre-render length check. Runs BEFORE everything to fail fast."""

    name = "ContentLengthChecker"
    priority = 0  # Runs BEFORE everything
    threshold = 1.0

    async def evaluate(
        self,
        optimized: OptimizedResume,
        job: JobPosting,
        source: ResumeSource,
    ) -> FilterResult:
        if optimized.html is None:
            return FilterResult(
                filter_name=self.name,
                passed=True,
                score=1.0,
                threshold=self.threshold,
                issues=[],
                suggestions=[],
            )

        pdf_bytes = optimized.pdf_bytes
        if pdf_bytes is None:
            try:
                render = await asyncio.to_thread(get_renderer().render, optimized.html)
                pdf_bytes = render.pdf_bytes
            except RenderError as e:
                return FilterResult(
                    filter_name=self.name,
                    passed=False,
                    score=0.0,
                    threshold=self.threshold,
                    issues=[f"Rendering failed: {str(e)}"],
                    suggestions=["Fix HTML content to allow rendering"],
                )

        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = len(doc)

        if page_count > 2:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                score=0.0,
                threshold=self.threshold,
                issues=[f"Resume is {page_count} pages - must be 1 page"],
                suggestions=["Reduce content to fit within 1 page"],
            )

        if page_count == 2:
            overflow_issue = check_page2_overflow(pdf_bytes)
            if overflow_issue:
                return FilterResult(
                    filter_name=self.name,
                    passed=False,
                    score=0.0,
                    threshold=self.threshold,
                    issues=[overflow_issue],
                    suggestions=[
                        "Content overflows to page 2",
                    ],
                )

        return FilterResult(
            filter_name=self.name,
            passed=True,
            score=1.0,
            threshold=self.threshold,
            issues=[],
            suggestions=[],
        )
