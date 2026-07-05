# Iteration-Cap Comparison — Results (Run 1)

**Date:** 2026-07-05
**Harness:** `tests/test_caps_comparison.py` (`uv run pytest ... -s -m benchmark`)
**Config:** optimizer v2, model `gemini-2.5-flash`, MAX_CAP=5, REPS=3, Vertex project `hr-breaker-498422` (us-central1)
**Runtime:** 1:28:28 (5308s)
**Design/plan:** `docs/plans/2026-07-04-caps-comparison-experiment-design.md`, `-plan.md`

> ⚠️ **Partial run.** The network dropped mid-run (DNS failures on `oauth2.googleapis.com`), so jobs 4–9 mostly failed/were skipped. **N=10 trajectories** collected, from only **3 jobs** (Fundraise Up, a BI Consultant role, kraken.com) + 1 rep of a 4th, against **one résumé**. Two subsequent re-run attempts crashed in the native PDF renderer (WeasyPrint/Pango access-violation; fontconfig has no config file on this Windows host), so a fuller run needs the renderer environment fixed first. Treat everything below as **indicative, not conclusive**.

## Report

```
CAP    QUALITY%(mean±sd)  ITERS_USED  CAP_BOUND%   TIME_s
 2       83.3 ± 6.2          2.0         100%       163.7
 3       85.4 ± 8.1          3.0          70%       239.8
 4       87.3 ± 8.0          3.7          60%       281.6
 5       81.0 ± 9.2          4.3           0%       337.1

Stopped at iteration:   3: ███ (3)    4: █ (1)    5: ██████ (6)

Per-dimension ordinal (iter0 → final, 0..2):
  ats_compatibility      1.90 → 2.00  up
  recruiter_scan         1.30 → 1.40  up
  bullet_quality         1.70 → 1.80  up
  seniority_calibration  1.60 → 1.60  --
  keyword_coverage       1.40 → 1.70  up
  structure              1.80 → 2.00  up
  concern_management     0.50 → 0.00  DOWN
  consistency            1.40 → 1.40  --
```

Per-run convergence stops: job1 [4,5,5], job2 [3,3,5], job3 [3,5,5], job4 [5, err, err].

## Interpretation (preliminary)

1. **The "convergence stops early → higher caps are dead weight" hypothesis was NOT confirmed here.** 6 of 10 runs ran all the way to the cap (iter 5); none stopped at 1–2. `CAP_BOUND%` is high (cap=2 → 100%, cap=3 → 70%). On this résumé the loop *wants* more than 2–3 iterations, and raising the cap changes the outcome.

2. **Quality peaks at cap=4 (87.3%), then regresses at cap=5 (81.0%).** The 5th iteration tends to make the result worse — consistent with the success-break path returning a weaker final iteration.

3. **Signal divergence.** The loop's internal convergence signal (`ordinal_sum` on `pdf_text`) allowed runs to reach iter 5, while the independent re-audit (averaged %, on HTML) says quality dropped there. This is the documented "two rulers" effect — but it hints at a real question in the patience logic: **why does patience=1 let runs reach iter 5?**

4. **Dimensions that move:** `keyword_coverage` (1.4→1.7) and `structure` (1.8→2.0) improve most; `seniority_calibration` and `consistency` never move.

## Actionable leads

- Default cap=3 may under-shoot (peak quality at 4), but cap=5 regresses → a hard cap around **4** looks best on this data.
- **Investigate why patience=1 doesn't stop earlier** (6/10 to the cap) — the most surprising signal; possible gap in the stopping logic.
- Fix the renderer/fontconfig environment so a full 9-job × 3-rep run can complete without native crashes.

## Reproduce

```
uv run pytest tests/test_caps_comparison.py -s -m benchmark
```
Requires Vertex creds + `output/Alexander Modestov.pdf` + `positions.txt`. Raw log of this run: `output/caps_comparison_run.0803.log` (gitignored).
