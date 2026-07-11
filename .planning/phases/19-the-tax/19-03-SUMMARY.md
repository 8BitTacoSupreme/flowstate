---
phase: 19-the-tax
plan: 03
status: complete
subsystem: bench-report
tags: [tax, tokens, latency, cost-per-success, track-2, report]

# Dependency graph
requires:
  - phase: 19-02
    provides: "RunSnapshot.tokens_in/tokens_out/cache_read (int) + wall_clock_s (float|None) + verify_pass (passed acceptance gates)"
provides:
  - "bench/report.py per-arm tax block (tokens/seconds totals) rendered in JSON + Rich + markdown, EXCLUDED from compounding_score"
  - "cost-per-success line = total tax ÷ summed verify_pass, labeled 'per verified acceptance gate' (never 'commit')"
affects: [19-VERD, cost-accounting, bench/report.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tax rendering lives entirely in bench/report.py — presentation-only, never imports/feeds bench/metrics.py (report.py contains no compute_scorecard reference)"
    - "Cost-per-success denominator = summed verify_pass; gates_passed==0 degrades to 'n/a' (never divide-by-zero)"
    - "Mirrors the existing judge exclusion note ('EXCLUDED from compounding_score') for the Track-2 tax"

key-files:
  created: []
  modified:
    - bench/report.py
    - tests/test_bench_compound.py

key-decisions:
  - "total_tokens for cost-per-success = tokens_in + tokens_out (billable consumption); cache_read reported separately but not folded into the per-gate cost"
  - "Denominator named after flowstate verify acceptance gates (summed verify_pass), NOT run/commit count — the pipeline produces artifacts, not commits (TAX-04). A dedicated test proves gates_passed != run count"
  - "wall_clock_s of None treated as 0.0 in the tax total (a dry run measures no time), matching the 19-02 carriage discipline"
  - "Tax added as a top-level 'tax' key in write_json alongside (not inside) the axes/score — the scorer payload is untouched; a test asserts compounding_score is unchanged"

patterns-established:
  - "T-19-05 repudiation guard: the tax block carries an explicit EXCLUDED-from-compounding_score note in JSON, Rich panel, and markdown so it can never be read as a Track-1 quality metric"
  - "T-19-06 DoS guard: zero passed gates -> 'n/a', no divide-by-zero"

requirements-completed: [TAX-03, TAX-04]

# Metrics
duration: ~9min
completed: 2026-07-11
---

# Phase 19 Plan 03: The Tax — Per-arm tokens/seconds in bench/report.py Summary

**`bench/report.py` now surfaces the measured consumption from Plan 02 as a per-arm Track-2 tax block (tokens_in/out/cache_read + seconds) in the JSON payload, the Rich report, and the markdown record — explicitly marked EXCLUDED from `compounding_score` — plus a cost-per-success line dividing total tokens/seconds by the count of passed `flowstate verify` acceptance gates, named honestly (never "commit") and degrading to "n/a" on zero gates.**

## Performance

- **Duration:** ~9 min
- **Tasks:** 2/2
- **Files modified:** 2 (1 source, 1 test)
- **Tests:** 1138 passed, 91.17% coverage (≥80% gate met)

## Accomplishments

- **Task 1 — per-arm tax totals (Track-2, excluded from score):** Added `_tax_totals(scorecard)` (sums `tokens_in`/`tokens_out`/`cache_read` as ints, `wall_clock_s` treating `None` as `0.0`) and `_tax_block(scorecard)` carrying the note `"Track-2 tax — EXCLUDED from compounding_score"` (mirroring the existing judge exclusion). `write_json` gained a top-level `"tax"` key; `render_report` prints a distinct cyan `Tax (Track-2)` panel after the scorecard panel; `_markdown_record` appends the totals. A test proves `compounding_score` is unchanged with the tax present, and a source-scan test asserts `report.py` never references `compute_scorecard` (tax stays presentation-only).
- **Task 2 — cost-per-success line:** Extended `_tax_block` with `gates_passed = sum(s.verify_pass ...)`, `tokens_per_verified_acceptance_gate` and `seconds_per_verified_acceptance_gate` = total tokens/seconds ÷ `gates_passed`, guarding `gates_passed == 0 → "n/a"`. The `cost_basis` field and all labels name the denominator as flowstate verify acceptance gates; a test asserts the tax JSON contains `"acceptance gate"` and never the substring `"commit"`. A second test proves the denominator is the summed `verify_pass` (7) rather than the run count (2). Rich panel + markdown render the cost-per-success line.

## Verification

- `uv run python -m pytest tests/test_bench_compound.py -x` — green (all 11 new tax tests pass).
- `uv run python -m pytest` (full suite) — 1138 passed, 91.17% coverage.
- `uv run ruff check bench/report.py bench/compound_eval.py` — clean.
- Sanity: tax numbers absent from `compute_scorecard`/`compounding_score` (report.py has no `compute_scorecard` reference, and the score-unchanged test); denominator label says "acceptance gate", never "commit". `compound_eval.main` already passes the scorecard to `render_report`/`write_json` — no collection change needed.

## TDD Gate Compliance

Both tasks followed RED → GREEN. Gate commits present in git log:
- Task 1: RED `a686ea5` → GREEN `a4b7b5e`
- Task 2: RED `bd9350b` → GREEN `02bb4c8`

## Deviations from Plan

None — plan executed exactly as written. (ruff-format reformatted `report.py` on the first Task 1 GREEN commit attempt; re-staged and committed with no behavior change.)

## Threat Surface

- **T-19-05 (Repudiation, mitigated):** the tax block carries an explicit `EXCLUDED from compounding_score` note in the JSON `tax.note`, the Rich panel header line, and the markdown record; the denominator is named as verify acceptance gates — honest reporting, cannot be read as a Track-1 metric.
- **T-19-06 (DoS, mitigated):** `gates_passed == 0` yields `"n/a"` in both cost fields — no divide-by-zero (dedicated test).
- **T-19-SC:** No new packages introduced.

No new threat surface beyond the plan's registered boundary (scorecard → report, in-process numeric fields only).

## Self-Check: PASSED

- `bench/report.py` — FOUND (`_tax_totals`, `_tax_block`, `_tax_panel`, `_tax_markdown_lines`; `tax` key in `write_json`)
- `tests/test_bench_compound.py` — FOUND (11 new tax/cost-per-gate tests)
- Commits a686ea5, a4b7b5e, bd9350b, 02bb4c8 — FOUND in git log
