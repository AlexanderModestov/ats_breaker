from pydantic import BaseModel

from hr_breaker.models.feedback import ValidationResult


class IterationContext(BaseModel):
    """Context passed to optimizer on each iteration."""

    iteration: int
    original_resume: str  # Original source LaTeX/text
    last_attempt: str | None = None  # Previous iteration's LaTeX output
    validation: ValidationResult | None = None  # Full filter results with scores

    def format_filter_results(self) -> str:
        """Format filter results for the optimizer prompt.

        Failed filters are listed first under a FAILED header so the LLM
        cannot miss them. Each failed filter shows score vs threshold and
        the gap (how much it must improve).
        """
        if not self.validation:
            return ""

        failed = [r for r in self.validation.results if not r.passed]
        passed = [r for r in self.validation.results if r.passed]

        lines: list[str] = []
        if failed:
            lines.append(f"FAILED FILTERS ({len(failed)}) — fix these:")
            for r in failed:
                gap = r.threshold - r.score
                lines.append(
                    f"  ❌ {r.filter_name}: {r.score:.2f} / {r.threshold:.2f} "
                    f"(needs +{gap:.2f} to pass)"
                )
                for issue in r.issues:
                    lines.append(f"     · {issue}")
                for suggestion in r.suggestions:
                    lines.append(f"     → {suggestion}")
        if passed:
            lines.append("")
            lines.append(f"PASSED FILTERS ({len(passed)}) — do NOT regress these:")
            for r in passed:
                lines.append(f"  ✅ {r.filter_name}: {r.score:.2f} / {r.threshold:.2f}")
        return "\n".join(lines)
