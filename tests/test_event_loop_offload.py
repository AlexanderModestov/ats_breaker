"""The optimization pipeline must not run blocking work on the event loop.

All optimizations share one uvicorn worker / one event loop, so any synchronous
WeasyPrint render, PyMuPDF rasterization, sentence-transformers encode or
Supabase write executed inline freezes *every* concurrent run, not just its own.
Each test here asserts the blocking call lands on a worker thread.

Keeping the renders off the main thread also keeps `renderer._render_lock`
(a threading.Lock, also taken by pydantic-ai's sync tool threads) from ever
being awaited by the event-loop thread.
"""

import threading

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hr_breaker.models import JobPosting, OptimizedResume, ResumeSource

MAIN_THREAD = threading.main_thread()


@pytest.fixture
def job_posting():
    return JobPosting(
        title="Engineer",
        company="Acme",
        description="Build things",
        requirements=["Python"],
        keywords=["python"],
    )


class _Recorder:
    """Records the thread each call ran on."""

    def __init__(self, result=None):
        self.threads: list[threading.Thread] = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.threads.append(threading.current_thread())
        return self.result

    @property
    def off_main(self) -> bool:
        assert self.threads, "recorded callable was never invoked"
        return all(t is not MAIN_THREAD for t in self.threads)


# --- VectorSimilarityMatcher: model load + encode ---------------------------


@pytest.mark.asyncio
async def test_vector_matcher_offloads_load_and_encode(monkeypatch, job_posting):
    """The first request pays a ~3s SentenceTransformer cold load, and every
    encode is CPU-bound (~0.2s); both must be offloaded."""
    from hr_breaker.filters import vector_similarity_matcher as vsm

    encode = _Recorder(result=_embeddings())
    fake_model = MagicMock()
    fake_model.encode = encode
    loader = _Recorder(result=fake_model)

    monkeypatch.setattr(vsm.VectorSimilarityMatcher, "_get_model", loader)

    optimized = OptimizedResume(source_checksum="x", html="<p>hi</p>", pdf_text="resume text")
    await vsm.VectorSimilarityMatcher().evaluate(
        optimized, job_posting, ResumeSource(content="x")
    )

    assert loader.off_main, "SentenceTransformer model load ran on the event loop"
    assert encode.off_main, "SentenceTransformer.encode ran on the event loop"


# --- ContentLengthChecker: fallback render ---------------------------------


@pytest.mark.asyncio
async def test_content_length_renders_off_main_thread(monkeypatch, job_posting):
    """When pdf_bytes is absent (editor path) the render must be offloaded."""
    from hr_breaker.filters import content_length as cl

    render = _Recorder(result=MagicMock(pdf_bytes=_one_page_pdf()))
    monkeypatch.setattr(cl, "get_renderer", lambda: MagicMock(render=render))

    optimized = OptimizedResume(source_checksum="x", html="<p>hi</p>", pdf_bytes=None)
    await cl.ContentLengthChecker().evaluate(
        optimized, job_posting, ResumeSource(content="x")
    )

    assert render.off_main, "ContentLengthChecker rendered on the event loop"


# --- combined_review: render + rasterize ----------------------------------


@pytest.mark.asyncio
async def test_combined_review_offloads_render_and_rasterize(monkeypatch, job_posting):
    """Both the WeasyPrint render and pdf_to_image (2x PyMuPDF rasterization)
    are CPU-bound and must be offloaded."""
    from hr_breaker.agents import combined_reviewer as cr

    render = _Recorder(result=MagicMock(pdf_bytes=b"%PDF-1.4", warnings=[], page_count=1))
    to_image = _Recorder(result=(b"png", 1))
    monkeypatch.setattr(cr, "get_renderer", lambda: MagicMock(render=render))
    monkeypatch.setattr(cr, "pdf_to_image", to_image)
    monkeypatch.setattr(cr, "get_combined_reviewer_agent", lambda: MagicMock())
    monkeypatch.setattr(
        cr, "with_model_retry", AsyncMock(return_value=MagicMock(output=MagicMock()))
    )

    optimized = OptimizedResume(source_checksum="x", html="<p>hi</p>", pdf_text="text")
    await cr.combined_review(optimized, job_posting)

    assert render.off_main, "combined_review rendered on the event loop"
    assert to_image.off_main, "pdf_to_image ran on the event loop"


# --- orchestration: render + PDF text extraction ---------------------------


@pytest.fixture
def stubbed_orchestration(monkeypatch):
    """optimize_for_job with every model call stubbed; returns
    (orchestration module, source, recorder for _render_and_extract)."""
    from hr_breaker import orchestration

    source = ResumeSource(content="Test resume content")
    optimized = OptimizedResume(
        source_checksum=source.checksum, html="<p>hi</p>", pdf_text="t", pdf_bytes=b"%PDF"
    )
    render_and_extract = _Recorder(result=optimized)

    monkeypatch.setattr(orchestration, "_render_and_extract", render_and_extract)
    monkeypatch.setattr(orchestration, "get_renderer", MagicMock())
    monkeypatch.setattr(
        orchestration, "optimize_resume_v2", AsyncMock(return_value=optimized)
    )
    monkeypatch.setattr(
        orchestration, "audit_resume", AsyncMock(side_effect=RuntimeError("no audit"))
    )
    monkeypatch.setattr(
        orchestration,
        "run_filters",
        AsyncMock(return_value=MagicMock(passed=True, results=[])),
    )
    return orchestration, source, render_and_extract


@pytest.mark.asyncio
async def test_orchestration_renders_off_main_thread(stubbed_orchestration, job_posting):
    """_render_and_extract does a WeasyPrint render plus PDF text extraction."""
    orchestration, source, render_and_extract = stubbed_orchestration

    await orchestration.optimize_for_job(source=source, job=job_posting, max_iterations=1)

    assert render_and_extract.off_main, "_render_and_extract ran on the event loop"


@pytest.mark.asyncio
async def test_optimize_for_job_awaits_async_on_iteration(stubbed_orchestration, job_posting):
    """The progress callback writes to Supabase, so it must be allowed to be a
    coroutine function — a sync callback can only block the loop."""
    orchestration, source, _ = stubbed_orchestration
    calls: list[int] = []

    async def on_iteration(iteration, opt, validation):
        calls.append(iteration)

    await orchestration.optimize_for_job(
        source=source, job=job_posting, max_iterations=1, on_iteration=on_iteration
    )

    assert calls == [0], "async on_iteration callback was not awaited"


# --- editor download route -------------------------------------------------


@pytest.mark.asyncio
async def test_editor_download_renders_off_main_thread(monkeypatch):
    """POST /{run_id}/download renders inside the request handler."""
    from hr_breaker.api.routes import editor

    render = _Recorder(result=MagicMock(pdf_bytes=b"%PDF-1.4"))
    monkeypatch.setattr(
        "hr_breaker.services.renderer.get_renderer", lambda: MagicMock(render=render)
    )
    monkeypatch.setattr(editor, "_get_completed_run", lambda *a, **k: {"status": "complete"})

    await editor.download_edited_pdf(
        run_id="r1",
        req=editor.DownloadRequest(html="<p>hi</p>"),
        user_id="u1",
        supabase=MagicMock(),
    )

    assert render.off_main, "editor download rendered on the event loop"


def _embeddings():
    """Two identical unit vectors — the matcher does numpy `@` on these."""
    import numpy as np

    return np.array([[1.0, 0.0], [1.0, 0.0]])


def _one_page_pdf() -> bytes:
    """Minimal real single-page PDF, so fitz page counting works on it."""
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data
