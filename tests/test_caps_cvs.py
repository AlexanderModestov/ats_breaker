"""Generate per-cap output CVs (cap 2/3/4/5) for each position.

For each job, runs the full optimize loop once per cap (max_iterations=2,3,4,5)
and saves the returned resume as output/comparison/<slug>_cap{cap}.pdf, then
audits it on the shared ruler. Unlike test_caps_comparison (which DERIVES the
2/3/4/5 outcomes from a single cap=5 trajectory), this runs each cap for real,
so every saved CV is exactly what that cap actually produces.

Inputs (env-overridable, both local + gitignored):
    CAPS_RESUME     resume PDF path      (default: output/Alexander Modestov.pdf)
    CAPS_POSITIONS  positions file path  (default: positions.txt)

Run:
    CAPS_RESUME="output/CV GM_Пятых ЮА.pdf" CAPS_POSITIONS=positions_edtech.txt \
        uv run pytest tests/test_caps_cvs.py -s -m benchmark

Skipped unless -m benchmark AND the resume PDF + positions file exist AND Vertex
credentials are configured.
"""

import contextlib
import io
import os
import time
from pathlib import Path

import pytest

from hr_breaker.config import get_settings
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer

from tests.test_optimizer_comparison import (
    OUTPUT_DIR,
    _bootstrap_vertex,
    _ingest_job,
    _slug,
    _split_positions,
    _with_retry,
    audit_resume_avg,
)

pytestmark = pytest.mark.benchmark

RESUME_PATH = Path(os.getenv("CAPS_RESUME", "output/Alexander Modestov.pdf"))
POSITIONS_PATH = Path(os.getenv("CAPS_POSITIONS", "positions.txt"))
CAPS = (2, 3, 4, 5)


async def test_caps_cvs(capsys, monkeypatch):
    if not RESUME_PATH.exists():
        pytest.skip(f"resume not found: {RESUME_PATH}")
    if not POSITIONS_PATH.exists():
        pytest.skip(f"positions file not found: {POSITIONS_PATH}")
    project = _bootstrap_vertex()
    if not project:
        pytest.skip("Vertex not configured")
    print(f"Vertex project: {project} ({get_settings().gcp_location})", flush=True)

    monkeypatch.setenv("OPTIMIZER_VERSION", "v2")
    monkeypatch.setenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []  # (label, cap, quality, iters, seconds, file_or_err)
    for i, raw in enumerate(jobs_raw, 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            print(f"[{i}/{len(jobs_raw)}] SKIPPED - {type(e).__name__}: {e}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        slug = _slug(label)
        print(f"[{i}/{len(jobs_raw)}] {label}", flush=True)
        for cap in CAPS:
            t = time.perf_counter()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    optimized, _, _ = await _with_retry(lambda cap=cap: optimize_for_job(
                        source=source, job=job, max_iterations=cap, parallel=True,
                    ))
                elapsed = time.perf_counter() - t
                pdf_bytes = optimized.pdf_bytes or HTMLRenderer().render(optimized.html).pdf_bytes
                pdf_path = OUTPUT_DIR / f"{slug}_cap{cap}.pdf"
                pdf_path.write_bytes(pdf_bytes)
                with contextlib.redirect_stdout(io.StringIO()):
                    q, _ = await audit_resume_avg(optimized.html, job)
                rows.append((label, cap, q, optimized.iteration + 1, elapsed, pdf_path.name))
                print(f"    cap {cap}: {q:.0f}% iters={optimized.iteration + 1} "
                      f"{elapsed:.1f}s -> {pdf_path.name}", flush=True)
            except Exception as e:
                rows.append((label, cap, None, None, time.perf_counter() - t,
                             f"ERR {type(e).__name__}: {e}"))
                print(f"    cap {cap}: ERROR {type(e).__name__}: {e}", flush=True)

    assert rows, "no runs completed"
    with capsys.disabled():
        print()
        print(f"{'job':<34}{'cap':>4}{'qual%':>8}{'iters':>7}{'time_s':>9}  file/err")
        print("-" * 78)
        for label, cap, q, iters, secs, tail in rows:
            qs = f"{q:.0f}%" if q is not None else "-"
            it = f"{iters}" if iters is not None else "-"
            print(f"{label[:32]:<34}{cap:>4}{qs:>8}{it:>7}{secs:>8.1f}s  {tail}")
