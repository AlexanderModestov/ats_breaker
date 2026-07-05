"""Phase-level speed benchmark for the resume optimization pipeline.

Two tests live here:

1. `test_pipeline_phase_breakdown` — single-pass pipeline timed per phase:
       parse_job → optimize → render_pdf → extract_text → filters
   No refine-iterations. Filter stage runs all filters in parallel (matches
   production `parallel=True`).

2. `test_optimize_thinking_budget_comparison` — runs `optimize` N times per
   fixture with different `gemini_thinking_budget` values to isolate the
   thinking-budget contribution to optimize latency. Activated by setting
   `BENCH_THINKING=8192,1024,0` (CSV of int budgets to compare). When this
   env var is set the full-phase test (1) is skipped to avoid double-billing
   the same fixtures.

Run:
    pytest tests/test_pipeline_benchmark.py -s -m benchmark
    BENCH_THINKING=8192,1024,0 pytest tests/test_pipeline_benchmark.py -s -m benchmark

Skipped unless `-m benchmark` AND env vars (SUPABASE_URL, SUPABASE_SERVICE_KEY,
ANTHROPIC_API_KEY) are set.
"""

import contextlib
import io
import os
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from hr_breaker.agents import optimize_resume, parse_job_posting
from hr_breaker.agents import optimizer as optimizer_module
from hr_breaker.filters import (
    ContentIntegrityChecker,
    DataValidator,
    KeywordMatcher,
    LLMChecker,
    VectorSimilarityMatcher,
)
from hr_breaker.models import IterationContext, ResumeSource
from hr_breaker.orchestration import run_filters
from hr_breaker.services.pdf_parser import extract_text_from_pdf
from hr_breaker.services.renderer import HTMLRenderer
from hr_breaker.services.supabase import SupabaseService

# Force filter registration (matches orchestration.py)
_ = DataValidator, LLMChecker, KeywordMatcher, VectorSimilarityMatcher, ContentIntegrityChecker

pytestmark = pytest.mark.benchmark

DEFAULT_N = 10
FETCH_MULTIPLIER = 5
PHASES = ("parse_job", "optimize", "render", "extract_text", "filters")


@dataclass
class Case:
    run_id: str
    cv_chars: int
    job_chars: int
    phases: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    @property
    def total(self) -> float:
        return sum(self.phases.values())


def _required_env() -> list[str]:
    return [
        v
        for v in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "ANTHROPIC_API_KEY")
        if not os.environ.get(v)
    ]


def _load_fixtures(service: SupabaseService, n: int) -> list[tuple[str, str, str]]:
    """Fetch up to `n` (run_id, cv_text, raw_job_text) tuples.

    Skips runs whose CV lacks `content_text` or whose `job_input` is empty.
    `job_input` is always present (NOT NULL in schema) but may be a URL we
    won't re-scrape — we still feed it as raw text to `parse_job_posting`,
    which falls back to LLM parsing on free-form text.
    """
    fetch_limit = max(n * FETCH_MULTIPLIER, n)
    rows = (
        service.client.table("optimization_runs")
        .select("id, cv_id, job_input, status, created_at")
        .eq("status", "complete")
        .order("created_at", desc=True)
        .limit(fetch_limit)
        .execute()
    ).data or []

    fixtures: list[tuple[str, str, str]] = []
    for row in rows:
        if len(fixtures) >= n:
            break
        if not row.get("job_input"):
            continue
        cv_row = (
            service.client.table("cvs")
            .select("content_text")
            .eq("id", row["cv_id"])
            .limit(1)
            .execute()
        ).data
        if not cv_row:
            continue
        content = cv_row[0].get("content_text")
        if not content:
            continue
        fixtures.append((row["id"], content, row["job_input"]))
    return fixtures


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


async def _time_one_case(run_id: str, cv_text: str, raw_job: str) -> Case:
    """Run the pipeline once on a single fixture, timing each phase."""
    case = Case(run_id=run_id, cv_chars=len(cv_text), job_chars=len(raw_job))

    # Suppress noisy prints from inner functions; we own the report.
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            # Phase 1: parse_job
            t = time.perf_counter()
            job, _ = await parse_job_posting(raw_job)
            case.phases["parse_job"] = time.perf_counter() - t

            # Phase 2: optimize (LLM)
            source = ResumeSource(content=cv_text)
            ctx = IterationContext(iteration=0, original_resume=cv_text)
            t = time.perf_counter()
            optimized = await optimize_resume(source, job, ctx)
            case.phases["optimize"] = time.perf_counter() - t

            # Phase 3: render PDF
            renderer = HTMLRenderer()
            t = time.perf_counter()
            render_result = renderer.render(optimized.html)
            case.phases["render"] = time.perf_counter() - t

            # Phase 4: extract text from PDF
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(render_result.pdf_bytes)
                pdf_path = Path(f.name)
            try:
                t = time.perf_counter()
                pdf_text = extract_text_from_pdf(pdf_path)
                case.phases["extract_text"] = time.perf_counter() - t
            finally:
                pdf_path.unlink()

            # Phase 5: all filters in parallel (matches prod parallel=True)
            optimized = optimized.model_copy(
                update={"pdf_text": pdf_text, "pdf_bytes": render_result.pdf_bytes}
            )
            t = time.perf_counter()
            await run_filters(optimized, job, source, parallel=True)
            case.phases["filters"] = time.perf_counter() - t
        except Exception as e:
            case.error = f"{type(e).__name__}: {e}"

    return case


def _print_report(cases: list[Case]) -> None:
    header = (
        f"{'#':<3}{'run_id':<10}{'cv':<7}{'job':<7}"
        + "".join(f"{p:>13}" for p in PHASES)
        + f"{'total':>10}{'  status'}"
    )
    print()
    print(header)
    print("─" * len(header))
    for i, c in enumerate(cases, 1):
        cells = [
            f"{c.phases[p]:>12.2f}s" if p in c.phases else f"{'—':>13}"
            for p in PHASES
        ]
        total = f"{c.total:>9.2f}s" if c.phases else f"{'—':>10}"
        status = c.error or "ok"
        print(
            f"{i:<3}{c.run_id[:8]:<10}{c.cv_chars:<7}{c.job_chars:<7}"
            f"{''.join(cells)}{total}  {status}"
        )

    # Aggregates per phase
    print("─" * len(header))
    print(
        f"{'agg':<3}{'':<10}{'':<7}{'':<7}"
        + "".join(f"{'avg/p50/p95':>13}" for _ in PHASES)
        + f"{'':<10}"
    )
    for label, fn in (("avg", statistics.mean), ("p50", lambda v: _percentile(v, 0.50)),
                      ("p95", lambda v: _percentile(v, 0.95))):
        cells = []
        for p in PHASES:
            vals = [c.phases[p] for c in cases if p in c.phases]
            cells.append(f"{fn(vals):>12.2f}s" if vals else f"{'—':>13}")
        totals = [c.total for c in cases if c.phases]
        total_cell = f"{fn(totals):>9.2f}s" if totals else f"{'—':>10}"
        print(f"{label:<3}{'':<10}{'':<7}{'':<7}{''.join(cells)}{total_cell}")

    # Share of total time per phase (avg basis)
    totals_avg = sum(
        statistics.mean([c.phases[p] for c in cases if p in c.phases])
        for p in PHASES
        if any(p in c.phases for c in cases)
    )
    if totals_avg > 0:
        print()
        print("Share of avg total time:")
        for p in PHASES:
            vals = [c.phases[p] for c in cases if p in c.phases]
            if vals:
                share = statistics.mean(vals) / totals_avg * 100
                print(f"  {p:<14} {share:>5.1f}%")

    errors = sum(1 for c in cases if c.error)
    if errors:
        print(f"\nerrors: {errors}/{len(cases)}")


async def test_pipeline_phase_breakdown(capsys):
    if os.environ.get("BENCH_THINKING"):
        pytest.skip("BENCH_THINKING set — using thinking-budget comparison test instead")
    missing = _required_env()
    if missing:
        pytest.skip(f"missing env vars: {', '.join(missing)}")

    n = int(os.environ.get("BENCH_N", DEFAULT_N))

    service = SupabaseService()
    fixtures = _load_fixtures(service, n)
    if not fixtures:
        pytest.skip("no eligible optimization_runs found in Supabase")

    cases = [await _time_one_case(rid, cv, job) for rid, cv, job in fixtures]

    with capsys.disabled():
        _print_report(cases)


# ─── thinking_budget comparison ──────────────────────────────────────────────


def _make_model_settings(budget: int):
    """Factory for a `get_model_settings`-shaped function fixed to one budget."""
    def fake() -> dict:
        return {"google_thinking_config": {"thinking_budget": budget}}
    return fake


async def _time_optimize_only(
    source: ResumeSource, job, budget: int, monkeypatch
) -> tuple[float | None, str | None]:
    """Run `optimize_resume` once with `gemini_thinking_budget` patched to `budget`."""
    monkeypatch.setattr(optimizer_module, "get_model_settings", _make_model_settings(budget))
    ctx = IterationContext(iteration=0, original_resume=source.content)
    with contextlib.redirect_stdout(io.StringIO()):
        t = time.perf_counter()
        try:
            await optimize_resume(source, job, ctx)
            return time.perf_counter() - t, None
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"


def _print_budget_comparison(
    budgets: list[int],
    fixtures_meta: list[tuple[str, int, int]],
    elapsed: dict[int, list[float | None]],
    errors: dict[int, list[str | None]],
) -> None:
    # Per-case row: one column per budget
    budget_cols = "".join(f"  iter_{b:<6}" for b in budgets)
    header = f"{'#':<3}{'run_id':<10}{'cv':<7}{'job':<7}{budget_cols}"
    print()
    print(header)
    print("─" * len(header))
    n_cases = len(fixtures_meta)
    for i in range(n_cases):
        rid, cv_chars, job_chars = fixtures_meta[i]
        cells = []
        for b in budgets:
            v = elapsed[b][i]
            cells.append(f"  {v:>8.2f}s " if v is not None else f"  {'err':>9} ")
        print(f"{i + 1:<3}{rid[:8]:<10}{cv_chars:<7}{job_chars:<7}{''.join(cells)}")

    # Aggregates per budget
    print()
    print(f"{'budget':<10}{'n':<5}{'avg':>10}{'p50':>10}{'p95':>10}"
          f"{'min':>10}{'max':>10}{'errors':>10}{'speedup':>10}")
    print("─" * 85)

    aggs: dict[int, dict[str, float] | None] = {}
    for b in budgets:
        oks = [v for v in elapsed[b] if v is not None]
        if not oks:
            aggs[b] = None
            continue
        aggs[b] = {
            "avg": statistics.mean(oks),
            "p50": _percentile(oks, 0.50),
            "p95": _percentile(oks, 0.95),
            "min": min(oks),
            "max": max(oks),
            "n": len(oks),
            "errors": sum(1 for e in errors[b] if e is not None),
        }

    # Use the slowest avg as the speedup baseline
    baseline_avg = max((a["avg"] for a in aggs.values() if a), default=None)

    for b in budgets:
        a = aggs[b]
        if a is None:
            print(f"{b:<10}{'all errored':<55}")
            continue
        speedup = f"{baseline_avg / a['avg']:.2f}×" if baseline_avg else "—"
        print(
            f"{b:<10}{a['n']:<5}"
            f"{a['avg']:>9.2f}s"
            f"{a['p50']:>9.2f}s"
            f"{a['p95']:>9.2f}s"
            f"{a['min']:>9.2f}s"
            f"{a['max']:>9.2f}s"
            f"{a['errors']:>10}"
            f"{speedup:>10}"
        )


async def test_optimize_thinking_budget_comparison(capsys, monkeypatch):
    raw = os.environ.get("BENCH_THINKING")
    if not raw:
        pytest.skip("BENCH_THINKING not set (e.g. BENCH_THINKING=8192,1024,0)")

    missing = _required_env()
    if missing:
        pytest.skip(f"missing env vars: {', '.join(missing)}")

    try:
        budgets = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        pytest.skip(f"BENCH_THINKING must be CSV of ints, got: {raw!r}")
    if not budgets:
        pytest.skip("BENCH_THINKING is empty after parsing")

    n = int(os.environ.get("BENCH_N", DEFAULT_N))

    service = SupabaseService()
    fixtures = _load_fixtures(service, n)
    if not fixtures:
        pytest.skip("no eligible optimization_runs found in Supabase")

    # Parse job once per fixture (shared across budgets — fair comparison).
    parsed: list[tuple[str, ResumeSource, object, int, int]] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for rid, cv_text, raw_job in fixtures:
            try:
                job, _ = await parse_job_posting(raw_job)
            except Exception:
                continue
            source = ResumeSource(content=cv_text)
            parsed.append((rid, source, job, len(cv_text), len(raw_job)))

    if not parsed:
        pytest.skip("could not parse any job postings")

    fixtures_meta = [(p[0], p[3], p[4]) for p in parsed]
    elapsed: dict[int, list[float | None]] = {b: [] for b in budgets}
    errors: dict[int, list[str | None]] = {b: [] for b in budgets}

    for budget in budgets:
        for _, source, job, _, _ in parsed:
            t, err = await _time_optimize_only(source, job, budget, monkeypatch)
            elapsed[budget].append(t)
            errors[budget].append(err)

    with capsys.disabled():
        _print_budget_comparison(budgets, fixtures_meta, elapsed, errors)
