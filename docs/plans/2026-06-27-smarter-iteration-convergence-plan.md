# Smarter Iteration Convergence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the resume optimization loop stop as soon as quality plateaus, using an independent per-iteration audit as the convergence signal, so it reaches the same-or-better CV in 1–2 iterations instead of 5.

**Architecture:** Add two pure ordinal-mapping helpers to `models/audit.py` (`ordinal_sum`, `no_dim_below_moderate`). Rewrite the loop in `orchestration.py` to (a) run an independent `audit_resume()` on each iteration's output, (b) track the best iteration by audit ordinal-sum, (c) stop early on a success target (filters pass AND no dimension below Moderate) or on convergence (patience 1, cap 3), and (d) refresh the optimizer's `audit_guidance` from each iteration's audit instead of the frozen baseline. Lower the API `max_iterations` default from 5 to 3.

**Tech Stack:** Python 3, Pydantic, pytest + pytest-asyncio, unittest.mock.

**Design doc:** `docs/plans/2026-06-27-smarter-iteration-convergence-design.md`

---

## Background facts (verified against current code)

- `AuditScore` (`src/hr_breaker/models/audit.py:5-17`) is categorical. Dimensions:
  `ats_compatibility` (ATS-Ready/ATS-Risky/ATS-Broken), `recruiter_scan`,
  `bullet_quality`, `keyword_coverage`, `structure`, `consistency`
  (Strong/Moderate/Weak), `seniority_calibration` (Aligned/Mismatched),
  `concern_management` (Strong/Moderate/Weak/NA). Plus `overall` and `top_fixes`
  (NOT used for scoring).
- `audit_resume(resume_content, job) -> AuditScore` and
  `audit_to_guidance(audit) -> str` exist in `agents/auditor.py` (lines 74, 96).
- The loop is `optimize_for_job()` in `orchestration.py:109-227`. Baseline audit +
  guidance: lines 143-152. Loop: lines 160-222. Current best-tracking is by
  `sum(filter scores)` (lines 213-218) — this gets replaced by audit ordinal-sum.
- `IterationContext` (`models/iteration.py:6-46`) already carries `validation` and
  `audit_guidance`, and already formats filter failures via `format_filter_results()`.
  So filter feedback already flows; only `audit_guidance` is currently frozen.
- API default lives at `api/schemas.py:73` — `max_iterations: int = Field(default=5, ...)`.
- Config default is already `max_iterations: int = 3` (`config.py:51`) — no change needed there.

---

## Task 1: Ordinal-mapping helpers in `models/audit.py`

**Files:**
- Modify: `src/hr_breaker/models/audit.py`
- Test: `tests/test_audit_scoring.py` (create)

**Step 1: Write the failing tests**

Create `tests/test_audit_scoring.py`:

```python
"""Tests for AuditScore ordinal mapping used by convergence."""

from hr_breaker.models.audit import AuditScore, ordinal_sum, no_dim_below_moderate


def _audit(**overrides):
    """An all-Strong baseline AuditScore, with per-dimension overrides."""
    base = dict(
        ats_compatibility="ATS-Ready",
        recruiter_scan="Strong",
        bullet_quality="Strong",
        seniority_calibration="Aligned",
        keyword_coverage="Strong",
        structure="Strong",
        concern_management="Strong",
        consistency="Strong",
        overall="Strong",
        top_fixes=[],
    )
    base.update(overrides)
    return AuditScore(**base)


def test_ordinal_sum_all_top_is_16():
    assert ordinal_sum(_audit()) == 16


def test_ordinal_sum_all_bottom_is_0():
    assert ordinal_sum(
        _audit(
            ats_compatibility="ATS-Broken",
            recruiter_scan="Weak",
            bullet_quality="Weak",
            seniority_calibration="Mismatched",
            keyword_coverage="Weak",
            structure="Weak",
            concern_management="Weak",
            consistency="Weak",
        )
    ) == 0


def test_na_concern_management_is_excluded():
    # 7 dims at Strong/Ready/Aligned (2 each) = 14, concern_management NA skipped
    assert ordinal_sum(_audit(concern_management="NA")) == 14


def test_ordinal_sum_mixed():
    # Risky=1, Moderate=1, Mismatched=0, rest Strong/Ready/Aligned=2
    a = _audit(
        ats_compatibility="ATS-Risky",   # 1
        recruiter_scan="Moderate",        # 1
        seniority_calibration="Mismatched",  # 0
    )
    # 1 + 1 + 2 + 0 + 2 + 2 + 2 + 2 = 12
    assert ordinal_sum(a) == 12


def test_no_dim_below_moderate_true_with_risky_and_moderate():
    # ATS-Risky and Moderate both count as Moderate-level (>= 1) → True
    assert no_dim_below_moderate(
        _audit(ats_compatibility="ATS-Risky", recruiter_scan="Moderate")
    ) is True


def test_no_dim_below_moderate_false_on_weak():
    assert no_dim_below_moderate(_audit(bullet_quality="Weak")) is False


def test_no_dim_below_moderate_false_on_ats_broken():
    assert no_dim_below_moderate(_audit(ats_compatibility="ATS-Broken")) is False


def test_no_dim_below_moderate_false_on_mismatched_seniority():
    assert no_dim_below_moderate(_audit(seniority_calibration="Mismatched")) is False


def test_no_dim_below_moderate_ignores_na():
    assert no_dim_below_moderate(_audit(concern_management="NA")) is True
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_audit_scoring.py -v`
Expected: FAIL with `ImportError: cannot import name 'ordinal_sum'`.

**Step 3: Implement the helpers**

Append to `src/hr_breaker/models/audit.py`:

```python
# Ordinal mapping for convergence scoring. Strong/Moderate/Weak map identically
# across all dimensions that use them; ATS and seniority have their own labels.
# `NA` (concern_management only) is excluded from both helpers.
_LEVEL = {
    "Strong": 2, "Moderate": 1, "Weak": 0,
    "ATS-Ready": 2, "ATS-Risky": 1, "ATS-Broken": 0,
    "Aligned": 2, "Mismatched": 0,
}

_DIMENSIONS = (
    "ats_compatibility",
    "recruiter_scan",
    "bullet_quality",
    "seniority_calibration",
    "keyword_coverage",
    "structure",
    "concern_management",
    "consistency",
)


def ordinal_sum(audit: AuditScore) -> int:
    """Sum each applicable dimension's ordinal level (0/1/2). Range 0..16
    (0..14 when concern_management is NA). `overall` is not counted."""
    total = 0
    for dim in _DIMENSIONS:
        value = getattr(audit, dim)
        if value == "NA":
            continue
        total += _LEVEL[value]
    return total


def no_dim_below_moderate(audit: AuditScore) -> bool:
    """True when every applicable dimension is Moderate-level or better
    (ATS-Risky counts as Moderate; ATS-Broken and Mismatched fail). NA skipped."""
    for dim in _DIMENSIONS:
        value = getattr(audit, dim)
        if value == "NA":
            continue
        if _LEVEL[value] < 1:
            return False
    return True
```

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_audit_scoring.py -v`
Expected: PASS (all 9 tests).

**Step 5: Commit**

```bash
git add src/hr_breaker/models/audit.py tests/test_audit_scoring.py
git commit -m "feat(audit): ordinal scoring helpers for convergence"
```

---

## Task 2: Convergence loop in `orchestration.py`

**Files:**
- Modify: `src/hr_breaker/orchestration.py` (imports + loop body `109-227`)
- Test: `tests/test_orchestration.py` (add a `TestConvergence` class)

**Step 1: Write the failing tests**

Add to `tests/test_orchestration.py`. These patch the LLM/render/filter calls so we
can control the audit score per iteration and assert stopping behaviour.

```python
from unittest.mock import AsyncMock, patch

from hr_breaker.models.audit import AuditScore
from hr_breaker.orchestration import optimize_for_job


def _audit(**overrides):
    base = dict(
        ats_compatibility="ATS-Ready", recruiter_scan="Strong",
        bullet_quality="Strong", seniority_calibration="Aligned",
        keyword_coverage="Strong", structure="Strong",
        concern_management="Strong", consistency="Strong",
        overall="Strong", top_fixes=[],
    )
    base.update(overrides)
    return AuditScore(**base)


def _validation(passed: bool):
    return ValidationResult(results=[
        FilterResult(filter_name="F", passed=passed, score=1.0 if passed else 0.0,
                     threshold=0.7)
    ])


class TestConvergence:
    @pytest.mark.asyncio
    async def test_stops_on_success_target(self, source_resume, job_posting):
        """Filters pass AND no dim below Moderate → stop after iteration 1."""
        optimized = OptimizedResume(html="<div/>", source_checksum=source_resume.checksum,
                                    pdf_text="text")
        with patch("hr_breaker.orchestration.optimize_resume", new=AsyncMock(return_value=optimized)), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(True))), \
             patch("hr_breaker.orchestration.audit_resume", new=AsyncMock(return_value=_audit())) as m_audit:
            await optimize_for_job(source_resume, job=job_posting, max_iterations=3)
        # baseline audit (1) + exactly one in-loop audit
        assert m_audit.await_count == 2

    @pytest.mark.asyncio
    async def test_stops_on_plateau_patience_1(self, source_resume, job_posting):
        """Filters never pass; audit plateaus → stop via patience after the
        2nd non-improving iteration (iterations run: 1 improving baseline,
        then 2 flat)."""
        optimized = OptimizedResume(html="<div/>", source_checksum=source_resume.checksum,
                                    pdf_text="text")
        # all iterations score the same (Weak somewhere so success never triggers)
        flat_audit = _audit(bullet_quality="Weak")
        with patch("hr_breaker.orchestration.optimize_resume", new=AsyncMock(return_value=optimized)), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(False))), \
             patch("hr_breaker.orchestration.audit_resume", new=AsyncMock(return_value=flat_audit)), \
             patch("hr_breaker.orchestration.optimize_resume_v2", new=AsyncMock(return_value=optimized)):
            await optimize_for_job(source_resume, job=job_posting, max_iterations=5)
        # iter0 sets best (improvement vs -1), iter1 flat (no_improve=1),
        # iter2 flat (no_improve=2 > 1) → break. optimize called 3 times, not 5.
        # asserted via call count below

    @pytest.mark.asyncio
    async def test_returns_best_not_last(self, source_resume, job_posting):
        """If a later iteration regresses, the earlier better one is returned."""
        good = OptimizedResume(html="<good/>", source_checksum=source_resume.checksum,
                               pdf_text="good")
        bad = OptimizedResume(html="<bad/>", source_checksum=source_resume.checksum,
                              pdf_text="bad")
        optimize_mock = AsyncMock(side_effect=[good, bad, bad])
        # good scores high (but a Weak prevents success), bad scores low
        audit_mock = AsyncMock(side_effect=[
            _audit(bullet_quality="Weak"),            # iter0: sum high
            _audit(bullet_quality="Weak", structure="Weak", recruiter_scan="Weak"),  # iter1 worse
            _audit(bullet_quality="Weak", structure="Weak", recruiter_scan="Weak"),
        ])
        with patch("hr_breaker.orchestration.optimize_resume", new=optimize_mock), \
             patch("hr_breaker.orchestration._render_and_extract", side_effect=lambda o, r: o), \
             patch("hr_breaker.orchestration.run_filters", new=AsyncMock(return_value=_validation(False))), \
             patch("hr_breaker.orchestration.audit_resume", new=audit_mock):
            result, _, _ = await optimize_for_job(source_resume, job=job_posting, max_iterations=3)
        assert result.html == "<good/>"
```

For `test_stops_on_plateau_patience_1`, capture the optimize mock and assert
`optimize_mock.await_count == 3` (add the mock as a named patch and assert after).

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_orchestration.py::TestConvergence -v`
Expected: FAIL (loop still runs to `max_iterations`; no audit-based best/stop).

**Step 3: Implement the loop changes**

3a. Update the import on `orchestration.py:11`:

```python
from hr_breaker.agents.auditor import audit_resume, audit_to_guidance
from hr_breaker.models.audit import ordinal_sum, no_dim_below_moderate
```

3b. Add a module constant near the top (after the imports block, ~line 34):

```python
PATIENCE = 1  # non-improving iterations tolerated before stopping
```

3c. Replace the best-tracking init (`orchestration.py:156-158`):

```python
    last_attempt: str | None = None
    best_optimized = None
    best_validation = None
    best_q = -1          # best audit ordinal-sum seen so far
    no_improve = 0
```

3d. Replace the tail of the loop body (`orchestration.py:213-222`, i.e. everything
from the `# Track the best-scoring iteration` comment through the
`if validation.passed:` early-exit) with:

```python
        # Independent quality audit of THIS iteration's output (trustworthy
        # convergence signal — not the optimizer's self-grade).
        audit = None
        q = None
        if optimized.pdf_text is not None:
            try:
                audit = await audit_resume(optimized.pdf_text, job)
                q = ordinal_sum(audit)
                print(f"  🎯 Audit: {audit.overall} (q={q}/16)")
            except Exception as e:
                logger.warning("Iteration audit failed: %s", e)

        # Success target: filters pass AND no dimension below Moderate.
        if validation.passed and audit is not None and no_dim_below_moderate(audit):
            best_optimized, best_validation, best_q = optimized, validation, q
            print(f"  ✅ Success target met (filters pass, q={q})")
            break

        # Track best by audit ordinal-sum; guard convergence with patience.
        improved = q is not None and q > best_q
        if improved or best_optimized is None:
            best_q = q if q is not None else best_q
            best_optimized = optimized
            best_validation = validation
            no_improve = 0
        else:
            no_improve += 1
            print(f"  ⏸️  No improvement ({no_improve}/{PATIENCE} tolerated)")
            if no_improve > PATIENCE:
                print(f"  🛑 Converged — stopping at iteration {i + 1}")
                break

        # Refresh guidance from THIS iteration's audit so the next round is told
        # what this attempt got wrong (was previously frozen at baseline).
        if audit is not None:
            audit_guidance = audit_to_guidance(audit)
```

3e. Update the closing log (`orchestration.py:224-225`) to reflect the new metric:

```python
    if best_optimized is not optimized:
        print(f"  ↩️  Returning best iteration (q={best_q}) — last was worse")
```

> Note: filter feedback already flows to the optimizer via `ctx.validation`
> (set from the loop's `validation` variable at `orchestration.py:170`) and
> `IterationContext.format_filter_results()`. Only `audit_guidance` was frozen;
> 3d fixes that. Do not concatenate filter text into `audit_guidance` — it would
> duplicate what `ctx.validation` already provides.

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_orchestration.py -v`
Expected: PASS (existing `run_filters` tests + new `TestConvergence`).

**Step 5: Run the full suite for regressions**

Run: `uv run pytest tests/test_orchestration.py tests/test_audit_scoring.py tests/test_optimizer_v2.py -v`
Expected: PASS.

**Step 6: Commit**

```bash
git add src/hr_breaker/orchestration.py tests/test_orchestration.py
git commit -m "feat(optimizer): convergence-based iteration stopping with independent audit"
```

---

## Task 3: Lower the API `max_iterations` default

**Files:**
- Modify: `src/hr_breaker/api/schemas.py:73`
- Test: `tests/test_optimize_routes.py` (add one assertion)

**Step 1: Write the failing test**

Add to `tests/test_optimize_routes.py`:

```python
from hr_breaker.api.schemas import OptimizeRequest


def test_optimize_request_default_max_iterations_is_3():
    req = OptimizeRequest(cv_id="x", job_input="some job")
    assert req.max_iterations == 3
```

**Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_optimize_routes.py -k default_max_iterations -v`
Expected: FAIL — currently 5.

**Step 3: Change the default**

`src/hr_breaker/api/schemas.py:73`:

```python
    max_iterations: int = Field(default=3, ge=1, le=10)
```

**Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_optimize_routes.py -k default_max_iterations -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/hr_breaker/api/schemas.py tests/test_optimize_routes.py
git commit -m "fix(api): lower default max_iterations from 5 to 3"
```

---

## Final verification

Run the full test suite:

```bash
uv run pytest -q
```

Expected: all green. If any pre-existing unrelated failures appear, report them
rather than fixing — they are out of scope (per CLAUDE.md §3, surgical changes).

## Out of scope (do not touch)

- `optimizer.py`, `optimizer_v2.py` — the convergence signal is the independent
  `audit_resume()`, version-agnostic. The v2 self-audit stays returned/stored,
  just untrusted for loop control.
- `auditor.py`, filters, `IterationContext` — unchanged.
- Making `PATIENCE` env-configurable — YAGNI until there's a reason to tune it.
