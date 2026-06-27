# Smarter Iteration Convergence — Design

**Date:** 2026-06-27
**Status:** Approved design, pending implementation plan

## Problem

The CV optimization loop runs a fixed number of iterations (default 3 in
config, but the API sends 5). In practice many iterations don't make the CV
better — the loop spins without improving the result, wasting cost and latency.

Root causes found in the current loop (`orchestration.py:160-222`):

1. **Frozen guidance.** The auditor runs once at baseline; the resulting
   `audit_guidance` is fed *identically* to every iteration. Iteration 3 gets
   the same instructions as iteration 1, blind to what it already tried.
2. **No convergence check.** The only early-exit is "all filters passed." If
   they never fully pass, all iterations burn even when quality plateaued at
   iteration 2.
3. **Weak quality signal.** The loop only knows `sum(filter scores)` and the
   binary filter gate. The richer 8-dimension `AuditScore` (returned by the v2
   optimizer) is stored and ignored — and even that is a *self-grade*, which
   inflates.

## Goal

Reach the same-or-better CV in **1–2 iterations instead of 5**, by trusting an
independent quality signal and stopping the moment we plateau.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Primary objective | Smarter **and** fewer iterations | Both convergence-based stopping and a tighter feedback loop. |
| Quality signal | **Filters (hard gate) + AuditScore (quality/convergence)** | Filters stay deterministic gate; audit captures "a better CV." |
| Score source | **Independent `audit_resume()` per iteration** | Self-grading inflates and defeats convergence. Net call count still drops because we cut iterations; an audit call is cheaper than a v2 optimize call. Reuses existing code. |
| Patience | **1** non-improving round tolerated | Allows one exploratory step; stops on the second. |
| Hard cap | **3** iterations | Backstop. |
| Success target | **Filters pass AND no dimension below Moderate** | Stronger than `overall == Strong`, realistically achievable. |
| ATS handling | ATS-Broken blocks; **ATS-Risky is acceptable** to stop | Keep it simple. |

## The new loop

Replaces `orchestration.py:160-222`:

```
baseline_audit = audit_resume(original)          # already exists
audit_guidance = audit_to_guidance(baseline_audit)
best = None;  best_q = -1;  no_improve = 0

for i in range(cap=3):
    optimized  = optimize(source, job, ctx)        # ctx carries last attempt + fresh guidance
    optimized  = render_and_extract(optimized)
    validation = run_filters(optimized)            # HARD GATE (unchanged)
    audit      = audit_resume(optimized)           # NEW: independent quality signal
    q          = ordinal_sum(audit)                # 0..16

    track_best(q, optimized, validation, audit)    # keep best by q

    # success target
    if validation.passed and no_dim_below_moderate(audit):
        break
    # convergence (patience 1)
    if q <= best_q_before_this_iter:
        no_improve += 1
        if no_improve > 1: break
    else:
        no_improve = 0

    # FRESH guidance for next round
    audit_guidance = audit_to_guidance(audit) + failed_filter_messages(validation)
    ctx = IterationContext(last_attempt=optimized, validation=validation,
                           audit_guidance=audit_guidance)

return best_optimized, best_validation
```

Best-iteration tracking and "return best, not last" stay as they are today.

### Two changes vs today

1. **Independent audit each iteration** → a real, trustworthy quality score
   (not the optimizer's self-grade).
2. **Guidance refreshed every round** from that audit's `top_fixes` + the
   iteration's filter failures — each iteration is told what *this* attempt got
   wrong, instead of replaying frozen baseline guidance.

## Scoring map

Each applicable dimension maps to an ordinal **0 / 1 / 2**:

| Dimension | 2 (good) | 1 (ok) | 0 (bad) |
|---|---|---|---|
| `ats_compatibility` | ATS-Ready | ATS-Risky | ATS-Broken |
| `recruiter_scan` | Strong | Moderate | Weak |
| `bullet_quality` | Strong | Moderate | Weak |
| `keyword_coverage` | Strong | Moderate | Weak |
| `structure` | Strong | Moderate | Weak |
| `consistency` | Strong | Moderate | Weak |
| `seniority_calibration` | Aligned | — | Mismatched |
| `concern_management` | Strong | Moderate | Weak *(or `NA` → excluded)* |

Two derived helpers (likely in `models/audit.py`):

```python
def ordinal_sum(a: AuditScore) -> int:
    # sum of all applicable dims; concern_management == "NA" is skipped
    # → range 0..16 (or 0..14 when concern_management is NA)

def no_dim_below_moderate(a: AuditScore) -> bool:
    # every applicable dim >= 1  (Mismatched=0 and ATS-Broken=0 fail; NA skipped)
```

Deliberate choices:

1. **`seniority_calibration` is 2-level** — Mismatched→0, Aligned→2, so a
   mismatch carries the full weight of a "Weak" dimension. A seniority mismatch
   is a serious problem and should hurt the score hard.
2. **`concern_management == "NA"` is excluded** from both the sum and the
   success check. Convergence still works because we only ever compare a resume
   to its own prior sum.
3. **`overall` is informational only** — not in the sum (would double-count the
   dimensions it summarizes) and not in the success check (we use
   per-dimension, which is stricter). Still shown in logs.

## Making each iteration count (the feedback loop)

`IterationContext` already carries `last_attempt`, `validation`, and
`audit_guidance` — the optimizer just isn't fed good values. The change: after
each iteration's independent audit, rebuild the guidance from *that* audit and
*that* iteration's filter failures:

```python
guidance = audit_to_guidance(audit)              # fresh top_fixes from THIS attempt
         + failed_filter_messages(validation)    # concrete "keyword X missing", "2 pages"
```

So iteration 2 is told: *"Here's the resume you just produced. It scored Weak on
bullet_quality and failed the length filter. Fix these specific things — keep
everything else."*

This converges fast because the model stops re-litigating already-solved
dimensions and spends effort only on what's still red.

**Regression guardrail:** we feed `last_attempt` + "keep everything else," and
we still track-best by ordinal sum and return best (not last). A bad rewrite
can't win — if iteration 2 tanks `consistency`, its lower sum means iteration 1
is returned, and patience-1 stops the flailing.

## Config changes

| Setting | Today | New | Notes |
|---|---|---|---|
| `max_iterations` (cap) | 3 (config) / **5 (API)** | **3** everywhere | The API schema default of 5 is the main culprit. |
| `patience` | — | **1**, hardcoded | One constant in the loop. Not env-exposed until needed (YAGNI). |

No new env vars. `max_iterations` stays runtime-overridable (CLI/API) as a
backstop.

**Optimizer version:** the convergence signal uses the *independent*
`audit_resume()`, which is version-agnostic — works identically for v1 and v2.
This change touches neither `optimizer.py` nor `optimizer_v2.py`. The v2
self-audit keeps being returned and stored; we just don't trust it for loop
control.

## Edge cases

- **First iteration always runs** — `best_q` starts at `-1`, so iteration 0
  always counts as improvement; patience can't trigger on round one.
- **`audit_resume()` fails (LLM error)** — treat that round as "no improvement"
  (increment patience) and keep the filter gate authoritative. Never crash the
  optimize flow on an audit hiccup.
- **Filters never pass + audit plateaus** — loop stops at patience/cap and
  returns the best-scoring iteration (same contract as today).
- **`concern_management` flips to/from NA between rounds** — sum compares
  same-resume history; a one-step denominator shift is tolerated by patience-1
  and can't cause a false success (success uses per-dim `>= Moderate`).

## Scope

**Touched:** `orchestration.py` (the loop) + the API schema default + a small
ordinal-mapping helper (likely `models/audit.py`).

**Unchanged:** `optimizer.py`, `optimizer_v2.py`, `auditor.py`, filters, and
`IterationContext`.
