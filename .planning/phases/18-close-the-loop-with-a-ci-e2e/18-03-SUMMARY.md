---
phase: 18-close-the-loop-with-a-ci-e2e
plan: 03
status: complete
subsystem: testing
tags: [pytest, bench, compound_eval, e2e, ci-safe, fail-loud]

# Dependency graph
requires:
  - phase: 16-17
    provides: "bench.compound_eval fail-loud producer gate (_EXIT_PRODUCER_ABSENT, _missing_producer, _ARM_PRODUCERS) and the --mode cheap loop"
provides:
  - "tests/test_bench_e2e_smoke.py — the HAR-05 'harness of harnesses works E2E' acceptance gate"
affects: [18-01, 18-02, ci]

# Tech tracking
tech-stack:
  added: []
  patterns: ["CI-safe E2E smoke via --mode cheap only", "arm-vocabulary coverage guard against silent drift"]

key-files:
  created: [tests/test_bench_e2e_smoke.py]
  modified: []

key-decisions:
  - "Producer-present/absent fixtures write repomix-pack.xml and wiki/*.md directly to disk instead of shelling out to repomix/npx, keeping the test CI-safe with no external tool or network dependency."
  - "No fresh bench.project.scaffold() call was needed for producer-present/absent state on the ORIGINAL --root: bench.compound_eval main() checks the producer gate against --root directly (before the internal worktree copy + re-scaffold), so writing producer files straight into tmp_path is sufficient and matches the real code path."
  - "Reused a single tmp_path per test function across multiple arms since main() never mutates its --root argument (all pipeline work happens in an internal tempfile.mkdtemp() worktree copy that's deleted after each run)."

patterns-established:
  - "Arm-coverage guard test: assert the union of tested arms == bench.compound_eval._ARM_PRODUCERS.keys() so a new arm added without an E2E smoke fails loud in CI (T-18-06 mitigation)."

requirements-completed: [HAR-05]

# Metrics
duration: 25min
completed: 2026-07-11
---

# Phase 18 Plan 03: Close the Loop with a CI E2E Summary

**CI-safe E2E smoke test proving all five bench arms (full/none/memory/pack/wiki) run green in `--mode cheap` and that pack/wiki fail loud with `_EXIT_PRODUCER_ABSENT` when their producer artifact is missing.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-11T02:10:00Z (approx)
- **Completed:** 2026-07-11T02:34:58Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- `tests/test_bench_e2e_smoke.py` exercises every `--layers` arm's plumbing through `bench.compound_eval.main`, entirely in `--mode cheap` (no live LLM/claude binary, no network)
- Asserts the fail-loud gate: `pack`/`wiki` arms with no producer artifact exit `bench.compound_eval._EXIT_PRODUCER_ABSENT` (referenced symbolically, never hardcoded `3`)
- Asserts `pack`/`wiki` arms return `0` once their producer artifact (`repomix-pack.xml`, `wiki/*.md`) is written directly to disk — proving the arm plumbing runs once satisfied
- Coverage-guard test (`test_every_arm_covered`) asserts the tested arm set equals `bench.compound_eval._ARM_PRODUCERS`, so a future arm added without an E2E smoke fails the guard rather than shipping silently untested

## Task Commits

Each task was committed atomically:

1. **Task 1: tests/test_bench_e2e_smoke.py — every-arm plumbing + fail-loud gate** - `759bd40` (test)

**Plan metadata:** (this commit)

## Files Created/Modified
- `tests/test_bench_e2e_smoke.py` - CI-safe E2E smoke covering all five arms + the fail-loud producer gate

## Decisions Made
- Producer artifacts (`repomix-pack.xml`, `wiki/overview.md`) are written directly as plain text/markdown rather than invoking repomix/npx, keeping the test hermetic and CI-safe per the environment constraints.
- Confirmed via code read of `bench/compound_eval.py` that the producer gate (`_missing_producer`) is checked against the raw `--root` argument BEFORE the internal `_worktree()` copy, so producer files placed directly under `tmp_path` are sufficient without needing to seed the internal worktree copy separately.
- A single `tmp_path` is reused across multiple arm invocations within a test function since `main()` never writes into its `--root` (all pipeline mutation happens in a `tempfile.mkdtemp()` copy that is deleted at the end of each `main()` call).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `uv run python -m pytest` modified `uv.lock` as a side effect of dependency resolution (unrelated to this plan's changes — no new dependency was added). Reverted with `git checkout -- uv.lock` before committing, per the environment note's instruction. `pyproject.toml` was never touched.
- Running `tests/test_bench_e2e_smoke.py` in isolation reports a coverage failure (41% < 80% gate) because the repo's coverage gate is computed across the FULL test suite, not a single file. The full-suite run (`uv run python -m pytest -q`) passed at 91.07% coverage with 1092 tests green, confirming no regression.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- HAR-05 is delivered: the milestone's closing E2E gate is in place and green.
- Plans 18-01 and 18-02 (if still incomplete) are unaffected — this plan had `depends_on: []` and ran independently against the existing Phase 16/17 fail-loud gate and cheap-mode loop.
- No blockers for milestone close once 18-01/18-02 land.

---
*Phase: 18-close-the-loop-with-a-ci-e2e*
*Completed: 2026-07-11*
