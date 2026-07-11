---
phase: 18-close-the-loop-with-a-ci-e2e
plan: 01
subsystem: testing
tags: [bootstrap, confidence-interval, statistics, bench, track-2, judge]
status: complete

# Dependency graph
requires:
  - phase: 17-no-silent-no-op-arms-plus-producers-wired-e2e
    provides: prepare_fixture per-arm producer wiring the replicate/compound_eval trial loop depends on
provides:
  - "bench/bootstrap.py: paired_bootstrap_ci, a seeded stdlib percentile-bootstrap CI helper"
  - "bench/replicate.py summary now carries bootstrap_ci_delta_vs_none[arm] (Track-2 only)"
affects: [18-02, 18-03, close-the-loop-e2e]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Track-2 statistics (judge-derived) stay isolated from bench/metrics.py's deterministic compounding_score — grep-gated in acceptance criteria and CI verification"
    - "Seeded local random.Random(seed) instance for deterministic bootstrap resampling (never module-level random.random())"

key-files:
  created:
    - bench/bootstrap.py
    - tests/test_bench_bootstrap.py
  modified:
    - bench/replicate.py
    - tests/test_bench_replicate.py

key-decisions:
  - "n==1 edge case handled by the general resampling path (not a special branch) — every size-1 resample draws the same value, so ci_low==ci_high==mean falls out naturally; only n==0 needs an explicit early return"
  - "Percentile CI indices use (resamples - 1) as the max index with round(), plus a defensive clamp so ci_low <= mean <= ci_high always holds even after 2-decimal rounding"
  - "bench/report.py intentionally left untouched per the plan's revised scope note — no caller in this phase routes the CI through report.write_json, so adding a judge_ci param there would be dead wiring"

requirements-completed: [HAR-04]

# Metrics
duration: 6min
completed: 2026-07-11
---

# Phase 18 Plan 01: Paired-Bootstrap CI Helper Summary

**Seeded stdlib paired-bootstrap CI (`bench/bootstrap.py`) wired into `replicate.py`'s Track-2 summary as `bootstrap_ci_delta_vs_none[arm]`, isolated from the deterministic compounding_score.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-11T02:24:21Z
- **Completed:** 2026-07-11T02:30:00Z
- **Tasks:** 2 (Task 1 = TDD: test + feat)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `bench/bootstrap.py::paired_bootstrap_ci` — pure stdlib (`random`, `statistics`), seeded via a local `random.Random(_BOOTSTRAP_SEED)`, never-raises, deterministic across repeated calls with the same seed
- Edge cases proven by test: empty input (`n=0`, `None` bounds), single value (degenerate `ci_low==ci_high==mean`), all-equal deltas (zero-width CI), non-numeric input (never raises, degrades to `None` bounds)
- `bench/replicate.py::main` now computes per-arm paired deltas (`arm_improvement_t - none_improvement_t`, indexed by trial, using whichever metric — raw or paired — Cohen's d already uses) and stores the CI'd result under `summary["bootstrap_ci_delta_vs_none"][arm]`, only when `none` is present in the run
- Verified isolation: `bench/replicate.py` never imports `bench.metrics` or references `compute_scorecard`; `bench/report.py` has a zero-diff `git diff --name-only` guard

## Task Commits

Each task was committed atomically (Task 1 followed the RED/GREEN TDD cycle per its `tdd="true"` frontmatter):

1. **Task 1 RED: failing test for paired-bootstrap CI helper** - `632e8a1` (test)
2. **Task 1 GREEN: seeded paired-bootstrap CI helper (bench/bootstrap.py)** - `1e5fe25` (feat)
3. **Task 2: wire the CI'd delta into replicate.py Track-2 output** - `8b44b83` (feat)

## Files Created/Modified
- `bench/bootstrap.py` - `paired_bootstrap_ci(deltas, *, resamples, seed, confidence) -> dict`; `_BOOTSTRAP_SEED = 1729`, `_DEFAULT_RESAMPLES = 2000`
- `tests/test_bench_bootstrap.py` - determinism, empty/n=1/all-equal edge cases, ci-bounds-bracket-mean, seed-changes-bounds-not-mean, never-raises-on-non-numeric
- `bench/replicate.py` - imports `paired_bootstrap_ci`; `main()` builds `summary["bootstrap_ci_delta_vs_none"]` alongside the existing `improvement_delta_vs_none` block
- `tests/test_bench_replicate.py` - `test_main_emits_bootstrap_ci_delta_vs_none` (monkeypatches `_run_trial` with fixed trajectories, asserts `ci_low <= mean <= ci_high` in the emitted JSON) and `test_main_omits_bootstrap_ci_when_none_arm_absent`

## Decisions Made
- No special-case branch for `n==1` — the general resampling loop already degenerates correctly (every size-1 with-replacement resample draws the single available value), keeping the implementation smaller per CLAUDE.md's simplicity-first rule.
- Percentile indices computed via `round(p * (resamples - 1))` with a defensive `ci_low <= mean <= ci_high` clamp, since 2-decimal rounding could otherwise place a bound a hundredth past the mean on rare inputs.
- Left `bench/report.py` untouched exactly as the plan's revision instructed — confirmed via `git diff --name-only bench/report.py` returning empty both before and after this plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `uv run python -m pytest --cov=bench --cov=flowstate` auto-modified `uv.lock` (uv resolving optional extras during the run). Reverted with `git checkout -- uv.lock` before each commit per the environment constraint (no dependency-file changes in this milestone). Not a deviation — a documented environment guard, not new functionality.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `bench/bootstrap.py` is available for Plan 02's `close_loop` one-command driver to surface the same CI'd delta in its own JSON.
- `bootstrap_ci_delta_vs_none` is proven present and well-formed via `tests/test_bench_replicate.py`; Plan 03's E2E smoke can assert on this key directly.
- No blockers.

---
*Phase: 18-close-the-loop-with-a-ci-e2e*
*Completed: 2026-07-11*

## Self-Check: PASSED

All created files and commit hashes verified present on disk / in git log.
