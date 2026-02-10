from hr_breaker.agents.content_integrity import check_content_integrity
from hr_breaker.config import get_settings
from hr_breaker.filters.base import BaseFilter
from hr_breaker.filters.registry import FilterRegistry
from hr_breaker.models import FilterResult, JobPosting, OptimizedResume, ResumeSource


@FilterRegistry.register
class ContentIntegrityChecker(BaseFilter):
    """Combined hallucination + AI detection in single LLM call."""

    name = "ContentIntegrityChecker"
    priority = 3

    @property
    def threshold(self) -> float:
        return get_settings().filter_hallucination_threshold

    async def evaluate(
        self,
        optimized: OptimizedResume,
        job: JobPosting,
        source: ResumeSource,
    ) -> FilterResult:
        hallucination_result, ai_result = await check_content_integrity(
            optimized, source
        )

        # Combine results: pass only if both checks pass
        passed = hallucination_result.passed and ai_result.passed

        # Combine issues and suggestions
        issues = hallucination_result.issues + ai_result.issues
        suggestions = hallucination_result.suggestions + ai_result.suggestions

        # Use minimum score (most conservative)
        score = min(hallucination_result.score, ai_result.score)

        return FilterResult(
            filter_name=self.name,
            passed=passed,
            score=score,
            threshold=self.threshold,
            issues=issues,
            suggestions=suggestions,
        )
