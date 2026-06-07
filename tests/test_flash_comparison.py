"""Baseline vs v1-flash vs v2-flash comparison.

Scores the original resume (no optimization), then runs v1 and v2 optimizers
both on gemini-2.5-flash, so the only variable is optimizer logic.

Run:
    uv run pytest tests/test_flash_comparison.py -s -m benchmark
"""

import contextlib
import io

import pytest

from tests.test_optimizer_comparison import (
    POSITIONS_PATH,
    RESUME_PATH,
    JobResult,
    _bootstrap_vertex,
    _ingest_job,
    _print_report,
    _run_version,
    _split_positions,
    audit_resume_avg,
    quality_score,
)
from hr_breaker.config import get_settings
from hr_breaker.models import ResumeSource
from hr_breaker.services.pdf_parser import extract_text_from_pdf

pytestmark = pytest.mark.benchmark

FLASH_MODEL = "gemini-2.5-flash"
VERSIONS = ("v1", "v2")
VERSION_CONFIG = {
    "v1": {"OPTIMIZER_VERSION": "v1", "OPTIMIZATION_MODEL": FLASH_MODEL},
    "v2": {"OPTIMIZER_VERSION": "v2", "OPTIMIZATION_MODEL": FLASH_MODEL},
}


async def test_flash_v1_v2_vs_baseline(capsys, monkeypatch):
    if not RESUME_PATH.exists():
        pytest.skip(f"resume not found: {RESUME_PATH}")
    if not POSITIONS_PATH.exists():
        pytest.skip(f"positions file not found: {POSITIONS_PATH}")
    project = _bootstrap_vertex()
    if not project:
        pytest.skip(
            "Vertex not configured: set GOOGLE_CLOUD_PROJECT / "
            "GOOGLE_APPLICATION_CREDENTIALS, or place the service-account JSON in repo root"
        )
    print(f"Vertex project: {project} ({get_settings().gcp_location})", flush=True)

    resume_text = extract_text_from_pdf(RESUME_PATH)
    source = ResumeSource(content=resume_text)
    jobs_raw = _split_positions(POSITIONS_PATH.read_text(encoding="utf-8"))
    if not jobs_raw:
        pytest.skip(f"no jobs parsed from {POSITIONS_PATH}")

    results: list[JobResult] = []
    skipped: list[str] = []
    for i, raw in enumerate(jobs_raw, 1):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            head = raw.splitlines()[0][:60]
            skipped.append(f"{head} ({type(e).__name__}: {e})")
            print(f"[{i}/{len(jobs_raw)}] SKIPPED {head} - {type(e).__name__}: {e}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        print(f"[{i}/{len(jobs_raw)}] {label} ...", flush=True)

        jr = JobResult(label=label)
        try:
            print("    base: scoring original (2 runs)...", flush=True)
            with contextlib.redirect_stdout(io.StringIO()):
                jr.baseline_quality, jr.baseline = await audit_resume_avg(resume_text, job, model=FLASH_MODEL)
            print(f"    base: {jr.baseline_quality:.0f}% {jr.baseline.overall}", flush=True)
        except Exception as e:
            print(f"    base: error {type(e).__name__}: {e}", flush=True)

        for v in VERSIONS:
            jr.by_version[v] = await _run_version(v, source, job, label, monkeypatch, VERSION_CONFIG, audit_model=FLASH_MODEL)
            r = jr.by_version[v]
            note = r.error or f"{r.total_time:.1f}s qual={r.quality:.0f}%"
            print(f"    {v}: {note}", flush=True)
        results.append(jr)

    with capsys.disabled():
        _print_report(results, VERSIONS)
        if skipped:
            print()
            print(f"skipped: {len(skipped)}")
            for s in skipped:
                print(f"  - {s}")
