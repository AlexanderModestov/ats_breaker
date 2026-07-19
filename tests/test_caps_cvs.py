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
import json
import os
import time
from pathlib import Path

import pytest

from hr_breaker.config import get_settings
from hr_breaker.models import ResumeSource
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer

from tests.conftest import POSITIONS_PATH, RESUME_PATH
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
CAPS = tuple(int(c) for c in os.getenv("CAPS_LIST", "2,3,4,5").split(","))
# Optional: run only one job (1-based index into the positions file) so a long
# campaign can be chunked across invocations — each stays short. Rows accumulate
# (deduped by job+cap) in a JSONL, and the markdown summary is regenerated from
# all rows collected so far, so chunks merge into one committable report.
CAPS_JOB = os.getenv("CAPS_JOB")
ROWS_PATH = Path("results/caps_cvs_rows.jsonl")
SUMMARY_PATH = Path("results/caps_cvs_summary.md")


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
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []  # (label, cap, quality, iters, seconds, file_or_err)

    def _persist(label, cap, q, iters, secs, tail):
        # Persist each row to the JSONL immediately so a chunk that is killed
        # mid-run still keeps its completed results.
        rows.append((label, cap, q, iters, secs, tail))
        with ROWS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "label": label, "cap": cap, "quality": q,
                "iters": iters, "seconds": secs, "tail": tail,
            }, ensure_ascii=False) + "\n")

    for i, raw in enumerate(jobs_raw, 1):
        if CAPS_JOB and str(i) not in {s.strip() for s in CAPS_JOB.split(",")}:
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                job = await _ingest_job(raw)
        except Exception as e:
            print(f"[{i}/{len(jobs_raw)}] SKIPPED - {type(e).__name__}: {e}", flush=True)
            continue
        label = f"{job.title} @ {job.company}".strip(" @")
        # Prefix with the position index: _slug() drops non-ASCII, so Cyrillic
        # titles would otherwise all collapse to the same slug and overwrite.
        slug = f"pos{i}_{_slug(label)}"
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
                _persist(label, cap, q, optimized.iteration + 1, elapsed, pdf_path.name)
                print(f"    cap {cap}: {q:.0f}% iters={optimized.iteration + 1} "
                      f"{elapsed:.1f}s -> {pdf_path.name}", flush=True)
            except Exception as e:
                _persist(label, cap, None, None, time.perf_counter() - t,
                         f"ERR {type(e).__name__}: {e}")
                print(f"    cap {cap}: ERROR {type(e).__name__}: {e}", flush=True)

    # Rows were persisted per-cap above. Regenerate the committable markdown
    # summary from ALL rows collected across chunks (deduped by job+cap so a
    # re-run overwrites its prior result).
    dedup = {}
    for line in ROWS_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            dedup[(r["label"], r["cap"])] = r
    all_rows = sorted(dedup.values(), key=lambda r: (r["label"], r["cap"]))

    md = [
        "# Per-cap CV benchmark — results",
        "",
        f"- Resume: `{RESUME_PATH}`",
        f"- Positions: `{POSITIONS_PATH}`",
        f"- Caps: {', '.join(str(c) for c in CAPS)}  (1 rep/job)",
        "- CV PDFs are saved locally in `output/comparison/` (gitignored, not committed).",
        "",
        "| Job | Cap | Quality % | Iters | Time (s) | File / Note |",
        "|-----|----:|----------:|------:|---------:|-------------|",
    ]
    for r in all_rows:
        qs = f"{r['quality']:.0f}" if r["quality"] is not None else "-"
        it = f"{r['iters']}" if r["iters"] is not None else "-"
        md.append(f"| {r['label']} | {r['cap']} | {qs} | {it} | {r['seconds']:.1f} | {r['tail']} |")
    SUMMARY_PATH.write_text("\n".join(md) + "\n", encoding="utf-8")

    with capsys.disabled():
        print()
        print(f"summary written to {SUMMARY_PATH} ({len(all_rows)} rows total)")
        print(f"{'job':<34}{'cap':>4}{'qual%':>8}{'iters':>7}{'time_s':>9}  file/err")
        print("-" * 78)
        for label, cap, q, iters, secs, tail in rows:
            qs = f"{q:.0f}%" if q is not None else "-"
            it = f"{iters}" if iters is not None else "-"
            print(f"{label[:32]:<34}{cap:>4}{qs:>8}{it:>7}{secs:>8.1f}s  {tail}")
