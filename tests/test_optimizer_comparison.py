"""Compare the two ATS optimizers (v1 vs v2) on speed and quality.

This is a measurement harness, not a pass/fail test. For each job posting it runs
the full `optimize_for_job` loop once under v1 and once under v2 (parsing the job
once, shared by both for fairness), then scores both final resumes with one
independent 8-dimension auditor so they sit on the same ruler. It prints a
side-by-side report and saves both final PDFs.

Inputs (local, gitignored):
- `output/Alexander Modestov.pdf` — source resume (text-extracted).
- `positions.txt` — vacancies separated by a line containing only `---`.

Outputs:
- `output/comparison/<job-slug>_v1.pdf` and `_v2.pdf`.

Run:
    uv run pytest tests/test_optimizer_comparison.py -s -m benchmark

Skipped unless `-m benchmark` AND the resume PDF + positions.txt exist AND Vertex
credentials (GOOGLE_CLOUD_PROJECT) are configured.
"""

import asyncio
import contextlib
import glob
import io
import json
import os
import re
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from pydantic_ai import Agent

from hr_breaker.agents import parse_job_posting
from hr_breaker.config import get_model_settings, get_settings
from hr_breaker.models import JobPosting, ResumeSource
from hr_breaker.models.audit import AuditScore
from hr_breaker.orchestration import optimize_for_job
from hr_breaker.services import scrape_job_posting
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer
from hr_breaker.utils.html_text import extract_text_from_html

pytestmark = pytest.mark.benchmark

RESUME_PATH = Path("output/Alexander Modestov.pdf")
POSITIONS_PATH = Path("positions.txt")
OUTPUT_DIR = Path("output/comparison")
VERSIONS = ("v1", "v2", "v2-flash")
VERSION_CONFIG: dict[str, dict[str, str]] = {
    "v1":       {"OPTIMIZER_VERSION": "v1"},
    "v2":       {"OPTIMIZER_VERSION": "v2"},
    "v2-flash": {"OPTIMIZER_VERSION": "v2", "OPTIMIZATION_MODEL": "gemini-2.5-flash"},
}
_ORIGINAL_OPTIMIZATION_MODEL = os.getenv("OPTIMIZATION_MODEL", "gemini-2.5-flash")


def _bootstrap_vertex() -> str | None:
    """Configure Vertex creds + project and init the SDK, like api/main.py.

    Resolves credentials from (in order) an existing GOOGLE_APPLICATION_CREDENTIALS,
    GOOGLE_APPLICATION_CREDENTIALS_JSON, or a repo-root service-account JSON. Derives
    the project from GOOGLE_CLOUD_PROJECT, settings, or the creds file's project_id.
    Returns the project id, or None if it can't be resolved.
    """
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if creds_json:
            f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            json.dump(json.loads(creds_json), f)
            f.flush()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name
        else:
            sa = next(iter(glob.glob("hr-breaker-*.json")), None)
            if sa:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(sa).resolve())

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or get_settings().gcp_project
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not project and creds_path and Path(creds_path).exists():
        with contextlib.suppress(Exception):
            project = json.loads(Path(creds_path).read_text()).get("project_id")
    if not project:
        return None

    # Make the project visible to the google-genai client (Vertex backend reads env)
    # and force Vertex/OAuth auth: a leftover GOOGLE_API_KEY would otherwise put the
    # client in Gemini-API key mode, which Vertex rejects (401 CREDENTIALS_MISSING).
    os.environ["GOOGLE_CLOUD_PROJECT"] = project
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    # gemini-3-*-preview models are served from the "global" endpoint, not the
    # us-central1 default. Honor an explicit GOOGLE_CLOUD_LOCATION, else use global.
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
    os.environ["GOOGLE_CLOUD_LOCATION"] = location
    import vertexai

    vertexai.init(project=project, location=location)
    return project


# ─── independent auditor ─────────────────────────────────────────────────────

AUDIT_PROMPT = r"""
You are a resume reviewer. You are given a FINISHED resume and a job posting.
Rate the resume across all 8 dimensions below for THIS specific job. Do NOT rewrite
or suggest HTML — only score. Be honest: if a dimension is Weak, say Weak.

1. ATS COMPATIBILITY (ATS-Ready / ATS-Risky / ATS-Broken)
   - Standard section headers ("Professional Experience", "Education", "Skills")
   - No tables, columns, text boxes, or graphics
   - Contact info in the body, target-role keywords present in the body

2. RECRUITER SCAN (Strong / Moderate / Weak) — 7-second F-pattern
   - Name and current title prominent; quantified achievement as first bullet of each role
   - Bullets not paragraphs; gaps present but not over-explained

3. BULLET QUALITY (Strong / Moderate / Weak)
   - XYZ formula ("Accomplished X measured by Y by doing Z"); passes the "so what?" test
   - Quantified (hard or proxy metrics); varied action verbs
   - Avoids "responsible for", "helped with", "worked on"

4. SENIORITY CALIBRATION (Aligned / Mismatched)
   - Verb tier matches candidate's evident level (IC/Manager/Director/VP+)
   - Impact scope grows across roles

5. KEYWORD COVERAGE (Strong / Moderate / Weak)
   - Job-posting keywords present in the body; skills ordered by relevance; specific beats generic

6. STRUCTURE (Strong / Moderate / Weak)
   - Single column; Summary -> Experience -> Education -> Skills; ~1 page; hooking 2-3 line summary

7. CONCERN MANAGEMENT (Strong / Moderate / Weak / NA)
   - Gaps framed neutrally; short tenures get a one-line rationale; career switch bridged
   - Use "NA" only if the resume presents no gaps, short tenures, or switches

8. CONSISTENCY (Strong / Moderate / Weak)
   - Tense (present current / past prior), punctuation, no first person, consistent dates

overall: Strong / Needs Work / Weak — holistic fit of this resume for this job.
top_fixes: the 3 highest-impact remaining improvements, priority-ordered.
"""


def get_auditor_agent() -> Agent:
    settings = get_settings()
    return Agent(
        f"google-vertex:{settings.gemini_pro_model}",
        output_type=AuditScore,
        system_prompt=AUDIT_PROMPT,
        model_settings=get_model_settings(),
    )


async def audit_resume(text_or_html: str, job: JobPosting) -> AuditScore:
    """Score a resume against a job posting on the 8-dimension rubric."""
    resume_text = extract_text_from_html(text_or_html) if "<" in text_or_html else text_or_html
    prompt = f"""## Job Posting
Title: {job.title}
Company: {job.company}
Requirements: {', '.join(job.requirements)}
Keywords: {', '.join(job.keywords)}
Description: {job.description}

## Finished Resume (rendered text)
{resume_text}

Rate this finished resume across all 8 dimensions for this job."""
    agent = get_auditor_agent()
    result = await agent.run(prompt)
    return result.output


# ─── scoring ─────────────────────────────────────────────────────────────────

_TRISTATE = {"Strong": 2, "Moderate": 1, "Weak": 0}
SCORE_MAPS: dict[str, dict[str, int]] = {
    "ats_compatibility": {"ATS-Ready": 2, "ATS-Risky": 1, "ATS-Broken": 0},
    "recruiter_scan": _TRISTATE,
    "bullet_quality": _TRISTATE,
    "seniority_calibration": {"Aligned": 2, "Mismatched": 0},
    "keyword_coverage": _TRISTATE,
    "structure": _TRISTATE,
    "concern_management": _TRISTATE,  # "NA" excluded from the total
    "consistency": _TRISTATE,
}
OVERALL_MAP = {"Strong": 2, "Needs Work": 1, "Weak": 0}
# Short column headers for the per-dimension detail table.
DIM_LABELS = {
    "ats_compatibility": "ats",
    "recruiter_scan": "recruiter",
    "bullet_quality": "bullets",
    "seniority_calibration": "seniority",
    "keyword_coverage": "keywords",
    "structure": "struct",
    "concern_management": "concern",
    "consistency": "consist",
}


def quality_score(audit: AuditScore) -> float:
    """Sum of dimension points / max possible (NA excluded) -> 0..100%."""
    earned = possible = 0
    for dim, mapping in SCORE_MAPS.items():
        val = getattr(audit, dim)
        if dim == "concern_management" and val == "NA":
            continue
        earned += mapping[val]
        possible += 2
    return 100.0 * earned / possible if possible else 0.0


# ─── result containers ───────────────────────────────────────────────────────


@dataclass
class VersionResult:
    version: str
    total_time: float
    iterations: int = 0
    filters_passed: int = 0
    filters_total: int = 0
    audit: AuditScore | None = None
    pdf_path: str | None = None
    error: str | None = None

    @property
    def quality(self) -> float:
        return quality_score(self.audit) if self.audit else 0.0


@dataclass
class JobResult:
    label: str
    baseline: AuditScore | None = None
    by_version: dict[str, VersionResult] = field(default_factory=dict)


# ─── helpers ─────────────────────────────────────────────────────────────────


def _split_positions(text: str) -> list[str]:
    """Split positions.txt into job chunks on lines containing only dashes."""
    chunks = re.split(r"(?m)^\s*-{3,}\s*$", text)
    return [c.strip() for c in chunks if c.strip()]


async def _ingest_job(raw: str) -> JobPosting:
    """Turn a raw chunk into a JobPosting, mirroring the production API path.

    A chunk that is just a URL is scraped first (scrape_job_posting), then parsed
    with the URL + hints — exactly like api/routes/optimize.py. Free-form text is
    parsed directly.
    """
    raw = raw.strip()
    url = raw if raw.startswith(("http://", "https://")) else None
    job_text, hints = raw, None
    if url:
        scraped = scrape_job_posting(url)  # raises ScrapingError/CloudflareBlockedError
        job_text, hints = scraped.text, scraped.hints
    job, _ = await parse_job_posting(job_text, url=url, hints=hints)
    return job


def _slug(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return s[:maxlen] or "job"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    sv = sorted(values)
    k = (len(sv) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (k - lo)


async def _with_retry(coro_fn, *, retries: int = 3, base_delay: float = 60.0):
    """Retry a coroutine on 429 RESOURCE_EXHAUSTED with exponential backoff."""
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt < retries and "429" in str(e):
                delay = base_delay * (2 ** attempt)
                print(f"      429 quota hit, retrying in {delay:.0f}s...", flush=True)
                await asyncio.sleep(delay)
            else:
                raise


async def _run_version(
    version: str, source: ResumeSource, job: JobPosting, label: str, monkeypatch
) -> VersionResult:
    """Run the full optimize loop under one optimizer version, save PDF, audit it."""
    cfg = VERSION_CONFIG[version]
    monkeypatch.setenv("OPTIMIZER_VERSION", cfg["OPTIMIZER_VERSION"])
    monkeypatch.setenv("OPTIMIZATION_MODEL", cfg.get("OPTIMIZATION_MODEL", _ORIGINAL_OPTIMIZATION_MODEL))
    get_settings.cache_clear()

    t = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            optimized, validation, _ = await _with_retry(
                lambda: optimize_for_job(source=source, job=job, parallel=True)
            )
        elapsed = time.perf_counter() - t
    except Exception as e:
        return VersionResult(version, time.perf_counter() - t, error=f"{type(e).__name__}: {e}")

    res = VersionResult(
        version=version,
        total_time=elapsed,
        iterations=optimized.iteration + 1,
        filters_passed=sum(1 for r in validation.results if r.passed),
        filters_total=len(validation.results),
    )

    # Save final PDF.
    if optimized.html:
        try:
            pdf_bytes = optimized.pdf_bytes or HTMLRenderer().render(optimized.html).pdf_bytes
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path = OUTPUT_DIR / f"{_slug(label)}_{version}.pdf"
            pdf_path.write_bytes(pdf_bytes)
            res.pdf_path = str(pdf_path)
        except Exception as e:  # rendering already happened in the loop; saving is best-effort
            res.error = f"save_pdf: {type(e).__name__}: {e}"

        # Independent audit on the final HTML.
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                res.audit = await _with_retry(lambda: audit_resume(optimized.html, job))
        except Exception as e:
            res.error = (res.error + " | " if res.error else "") + f"audit: {type(e).__name__}: {e}"

    return res


# ─── reporting ───────────────────────────────────────────────────────────────


def _print_report(results: list[JobResult]) -> None:
    # 1. Per-job rows.
    header = (
        f"{'job':<34}{'ver':<8}{'time':>9}{'iters':>7}{'filters':>9}"
        f"{'qual%':>8}{'   d%':>7}{'  overall':<14}"
    )
    print()
    print(header)
    print("-" * len(header))
    for jr in results:
        label = jr.label[:32]
        base_q = quality_score(jr.baseline) if jr.baseline else None

        if jr.baseline:
            print(
                f"{label:<34}{'base':<8}{'-':>9}{'-':>7}{'-':>9}"
                f"{base_q:>7.0f}%{'':>7}  {jr.baseline.overall:<14}"
            )

        for v in VERSIONS:
            r = jr.by_version.get(v)
            if r is None or r.audit is None:
                status = (r.error if r else "missing") or "no audit"
                t = f"{r.total_time:>8.1f}s" if r else f"{'-':>9}"
                print(f"{'':>34}{v:<8}{t}{'':>7}{'':>9}{'':>8}{'':>7}  {status[:30]}")
                continue
            delta = f"{r.quality - base_q:>+6.0f}%" if base_q is not None else ""
            print(
                f"{'':>34}{v:<8}"
                f"{r.total_time:>8.1f}s"
                f"{r.iterations:>7}"
                f"{r.filters_passed:>4}/{r.filters_total:<4}"
                f"{r.quality:>7.0f}%"
                f"{delta:>7}"
                f"  {r.audit.overall:<14}"
            )

    # 2. Per-dimension detail per job.
    dims = list(DIM_LABELS)
    dim_header = f"{'':<10}" + "".join(f"{DIM_LABELS[d]:>11}" for d in dims)
    for jr in results:
        if not jr.baseline and not any(jr.by_version.get(v) and jr.by_version[v].audit for v in VERSIONS):
            continue
        print()
        print(f"  {jr.label}")
        print("  " + dim_header)
        if jr.baseline:
            cells = "".join(f"{getattr(jr.baseline, d):>11}" for d in dims)
            print(f"  {'base':<10}{cells}")
        for v in VERSIONS:
            r = jr.by_version.get(v)
            if not r or not r.audit:
                continue
            cells = "".join(f"{getattr(r.audit, d):>11}" for d in dims)
            print(f"  {v:<10}{cells}")

    # 3. Aggregates.
    baselines = [jr.baseline for jr in results if jr.baseline]
    avg_base = statistics.mean(quality_score(b) for b in baselines) if baselines else None

    print()
    print("=== aggregates ===")
    agg_header = (
        f"{'ver':<8}{'n':>4}{'avg_t':>9}{'p50_t':>9}{'p95_t':>9}"
        f"{'avg_iter':>10}{'avg_qual':>10}{'avg_d':>8}"
    )
    print(agg_header)
    print("-" * len(agg_header))
    if avg_base is not None:
        print(f"{'base':<8}{len(baselines):>4}{'':>9}{'':>9}{'':>9}{'':>10}{avg_base:>9.0f}%{'':>8}")
    for v in VERSIONS:
        rs = [jr.by_version[v] for jr in results if jr.by_version.get(v) and jr.by_version[v].audit]
        if not rs:
            print(f"{v:<8}{'no successful runs':<40}")
            continue
        times = [r.total_time for r in rs]
        avg_q = statistics.mean([r.quality for r in rs])
        delta_str = f"{avg_q - avg_base:>+7.0f}%" if avg_base is not None else ""
        print(
            f"{v:<8}{len(rs):>4}"
            f"{statistics.mean(times):>8.1f}s"
            f"{_percentile(times, 0.50):>8.1f}s"
            f"{_percentile(times, 0.95):>8.1f}s"
            f"{statistics.mean([r.iterations for r in rs]):>10.1f}"
            f"{avg_q:>9.0f}%"
            f"{delta_str:>8}"
        )

    # Win counts per job (best quality version).
    qual_wins = {v: 0 for v in VERSIONS}
    speed_wins = {v: 0 for v in VERSIONS}
    ties = comparable = 0
    for jr in results:
        audited = [v for v in VERSIONS if jr.by_version.get(v) and jr.by_version[v].audit]
        if len(audited) < 2:
            continue
        comparable += 1
        best_q = max(jr.by_version[v].quality for v in audited)
        winners = [v for v in audited if jr.by_version[v].quality == best_q]
        if len(winners) > 1:
            ties += 1
        else:
            qual_wins[winners[0]] += 1
        fastest = min(audited, key=lambda v: jr.by_version[v].total_time)
        speed_wins[fastest] += 1
    print()
    print(f"comparable jobs: {comparable}")
    if comparable:
        print("  quality wins: " + ", ".join(f"{v} {qual_wins[v]}" for v in VERSIONS) + (f", ties {ties}" if ties else ""))
        print("  speed wins:   " + ", ".join(f"{v} {speed_wins[v]}" for v in VERSIONS))


# ─── the test ────────────────────────────────────────────────────────────────


async def test_optimizer_v1_v2_comparison(capsys, monkeypatch):
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
            print(f"    base: scoring original...", flush=True)
            with contextlib.redirect_stdout(io.StringIO()):
                jr.baseline = await _with_retry(lambda: audit_resume(resume_text, job))
            print(f"    base: {quality_score(jr.baseline):.0f}% {jr.baseline.overall}", flush=True)
        except Exception as e:
            print(f"    base: error {type(e).__name__}: {e}", flush=True)

        for v in VERSIONS:
            jr.by_version[v] = await _run_version(v, source, job, label, monkeypatch)
            r = jr.by_version[v]
            note = r.error or f"{r.total_time:.1f}s qual={r.quality:.0f}%"
            print(f"    {v}: {note}", flush=True)
        results.append(jr)

    with capsys.disabled():
        _print_report(results)
        if skipped:
            print()
            print(f"skipped jobs (scrape/parse failed): {len(skipped)}")
            for s in skipped:
                print(f"  - {s}")
