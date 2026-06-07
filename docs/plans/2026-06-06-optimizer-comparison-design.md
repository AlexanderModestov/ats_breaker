# Optimizer v1 vs v2 Comparison Harness — Design

**Date:** 2026-06-06
**Goal:** Measure and compare the two ATS optimizers (v1, v2) on the same resume × job postings, on **speed** and **quality**, and emit a side-by-side report.

This is a *measurement harness*, not a pass/fail test. No production code changes — it drives the existing `optimize_for_job` loop and adds an independent quality judge.

---

## Inputs (local, gitignored)

- **Resume:** `output/Alexander Modestov.pdf` — text extracted via `extract_text_from_pdf`. (`output/` already gitignored.)
- **Jobs:** `positions.txt` at repo root — multiple vacancies separated by a line containing only `---`. Each chunk is raw text. (Added to `.gitignore`.)
- **Saved outputs:** final PDFs written to `output/comparison/<job-slug>_v1.pdf` and `_v2.pdf`.

## Data flow (per job)

1. Load resume text once; split `positions.txt` on `---` → list of raw job chunks.
2. Ingest each chunk **once** (shared by v1 and v2; ingestion is not under test), mirroring the production API path in `api/routes/optimize.py`: if the chunk is a URL, `scrape_job_posting(url)` → text + hints; then `parse_job_posting(text, url=url, hints=hints)` → `JobPosting`. Free-form text is parsed directly. Chunks whose scrape/parse fails (e.g. Cloudflare-protected, JS-only, Telegram) are skipped and listed in the report — the same limitation the app surfaces to users.
3. **v1:** set `OPTIMIZER_VERSION=v1`, `get_settings.cache_clear()`, time `optimize_for_job(source, job=job)` end-to-end (includes refine loops + filters). Capture final `OptimizedResume`, `ValidationResult`, iterations = `optimized.iteration + 1`.
4. **v2:** same with `OPTIMIZER_VERSION=v2`.
5. **Audit both** with one independent `audit_resume(html, job)` → `AuditScore` — identical ruler for v1 and v2.
6. Save both PDFs; record a result row.

## Independent auditor (in-harness)

- `async def audit_resume(html, job) -> AuditScore`.
- Pydantic-AI `Agent(f"google-vertex:{settings.gemini_pro_model}", output_type=AuditScore, ...)`.
- System prompt = a **scoring-only** restatement of the same 8-dimension rubric v2 uses (rate the finished resume; no rewrite). Reuses the existing `AuditScore` model.
- Independent of v2's *self*-audit (which only grades its own work and has no v1 equivalent).
- Lives in the harness module — not added to `src/` production surface (YAGNI).

## Scoring

**Speed:** `total_time` (wall-clock of full loop), `iterations`.

**Quality** — map categorical `AuditScore` to points:

| Dimension | Mapping |
|---|---|
| ats_compatibility | ATS-Ready=2, ATS-Risky=1, ATS-Broken=0 |
| recruiter_scan, bullet_quality, keyword_coverage, structure, consistency | Strong=2, Moderate=1, Weak=0 |
| seniority_calibration | Aligned=2, Mismatched=0 |
| concern_management | Strong=2, Moderate=1, Weak=0, NA=excluded |
| overall | Strong=2, Needs Work=1, Weak=0 (shown, not summed) |

`quality_score` = summed points ÷ max possible (excluding NA) → 0–100%.

**Winner:** higher `quality_score` wins quality; lower `total_time` wins speed (reported separately).

## Report (stdout via `capsys.disabled()`)

1. Per-job rows: version, time, iters, filters-passed, qual%, overall.
2. Per-dimension detail table: v1 vs v2 across all 8 dimensions.
3. Aggregates: avg/p50/p95 time per version, avg quality%, win counts, avg iterations.

Reuses `_percentile` + table style from `test_pipeline_benchmark.py`.

## File / gates

- New: `tests/test_optimizer_comparison.py` (`tests/` is gitignored — local tool).
- `.gitignore`: add `positions.txt`.
- Skips unless: `-m benchmark`, resume PDF + `positions.txt` exist, and GCP/Vertex creds present.
- Run: `uv run pytest tests/test_optimizer_comparison.py -s -m benchmark`

## Verification

1. `audit_resume` returns valid `AuditScore` for sample HTML (mocked unit check).
2. `positions.txt` splitter returns N jobs from a known fixture string (no LLM).
3. Full harness on real files → report + saved PDFs.
