from hr_breaker.config import get_settings
from hr_breaker.filters.base import BaseFilter
from hr_breaker.filters.registry import FilterRegistry
from hr_breaker.models import FilterResult, JobPosting, OptimizedResume, ResumeSource

try:
    from sentence_transformers import SentenceTransformer

    _HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    _HAS_SENTENCE_TRANSFORMERS = False


@FilterRegistry.register
class VectorSimilarityMatcher(BaseFilter):
    """Vector similarity filter using sentence-transformers."""

    name = "VectorSimilarityMatcher"
    priority = 6
    _model = None
    _model_name = None

    @property
    def threshold(self) -> float:
        return get_settings().filter_vector_threshold

    @classmethod
    def _get_model(cls):
        settings = get_settings()
        model_name = settings.sentence_transformer_model
        if cls._model is None or cls._model_name != model_name:
            if _HAS_SENTENCE_TRANSFORMERS:
                cls._model = SentenceTransformer(model_name)
                cls._model_name = model_name
        return cls._model

    async def evaluate(
        self,
        optimized: OptimizedResume,
        job: JobPosting,
        source: ResumeSource,
    ) -> FilterResult:
        if not _HAS_SENTENCE_TRANSFORMERS:
            return FilterResult(
                filter_name=self.name,
                passed=True,
                score=1.0,
                threshold=self.threshold,
                issues=["sentence-transformers not installed, skipping"],
                suggestions=[],
            )

        if optimized.pdf_text is None:
            return FilterResult(
                filter_name=self.name,
                passed=False,
                score=0.0,
                threshold=self.threshold,
                issues=["No PDF text available"],
                suggestions=["Ensure PDF compilation succeeds"],
            )

        model = self._get_model()
        resume_text = optimized.pdf_text
        job_text = f"{job.title} {job.description or ''} {' '.join(job.requirements)}"

        embeddings = model.encode([resume_text, job_text])
        similarity = float(
            embeddings[0]
            @ embeddings[1]
            / (
                (embeddings[0] @ embeddings[0]) ** 0.5
                * (embeddings[1] @ embeddings[1]) ** 0.5
            )
        )

        # Cosine similarity of MiniLM embeddings of resume vs job text.
        # Non-negative in practice; compare directly against the threshold.
        score = max(0.0, similarity)

        issues = []
        suggestions = []

        if score < self.threshold:
            issues.append(
                f"Low semantic vector similarity to job posting ({score:.2f})"
            )

        return FilterResult(
            filter_name=self.name,
            passed=score >= self.threshold,
            score=score,
            threshold=self.threshold,
            issues=issues,
            suggestions=suggestions,
        )
