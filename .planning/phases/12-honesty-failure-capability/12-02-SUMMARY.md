---
phase: 12-honesty-failure-capability
plan: 02
subsystem: pipeline-adapters
tags: [error-handling, tool-adapters, honesty, research, strategy]

# Dependency graph
requires:
  - phase: 12-honesty-failure-capability (plan 01)
    provides: "_run_step's existing success/BLOCKED/StepFailed routing (unchanged, reused here)"
provides:
  - "research.execute() returns success=False when every topic exhausts its retries"
  - "strategy.pressure_test() returns success=False on empty or failed bridge output"
  - "gsd_adapter module docstring matches its deterministic-only behavior"
affects: [13-mechanism-work, orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Adapter honesty: count real successes, not just attempt exhaustion, before deciding success/failure"
    - "Failure paths write no artifact (strategy) or write the failure record but flag it non-success (research)"

key-files:
  created: []
  modified:
    - flowstate/tools/research.py
    - flowstate/tools/strategy.py
    - flowstate/tools/gsd_adapter.py
    - tests/test_tools.py

key-decisions:
  - "research.execute(): success=False only when produced==0 (all topics failed); partial success (>=1 topic) stays success=True with the per-topic failure notice preserved in the report"
  - "strategy.pressure_test(): replaced the bridge_to_result(br) passthrough (which leaked br.success=True on empty output) with an explicit success=False return; error defaults to 'strategy produced empty output' when the bridge itself didn't report one"
  - "gsd_adapter.py: docstring-only fix, no bridge path added — HON-06 explicitly forbids adding unused LLM enrichment"

patterns-established:
  - "Adapter failure honesty: return success=False whenever the artifact represents a failure record, not real output, so orchestrator._run_step's existing BLOCKED routing fires correctly"

requirements-completed: [HON-03, HON-04, HON-06]

# Metrics
duration: 25min
completed: 2026-07-10
---

# Phase 12 Plan 02: Adapter Failure Honesty Summary

**research and strategy adapters now return `success=False` on genuine failure instead of always reporting success — research fails only when every topic is exhausted, strategy fails on empty/failed bridge output and writes no artifact, and the gsd_adapter docstring no longer claims an LLM path that doesn't exist.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-10T16:25:00Z
- **Completed:** 2026-07-10T16:50:26Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- `ResearchAdapter.execute()` counts topics that produced real bridge output; returns `ToolResult(success=False, error=<failed-topics summary>)` when zero topics succeed, while partial success (>=1 topic) still returns `success=True` with the failure notice for the failed topic(s) intact in `report.md`
- `StrategyAdapter.pressure_test()` returns `ToolResult(success=False, ...)` for both an outright bridge failure and a bridge success with empty/whitespace output — `strategy.md` is never written on this path (only the success branch writes it, unchanged)
- `gsd_adapter.py` module docstring no longer claims "optional LLM enrichment"; now accurately describes deterministic delegation to `context.py`

## Task Commits

Each task was committed atomically:

1. **Task 1: research.execute() fails when all topics fail (HON-03)** - `5978fc4` (fix)
2. **Task 2: strategy fails on empty/failed output + gsd docstring fix (HON-04, HON-06)** - `82d1105` (fix)
3. **Task 3: Reconcile tests encoding old adapter behavior, add failure-path tests** - `b4f3f20` (test)

**Plan metadata:** committed with this SUMMARY.md

## Files Created/Modified
- `flowstate/tools/research.py` - `execute()` now tracks `produced` count and `failed_topics`; returns `success=False` only when `produced == 0`
- `flowstate/tools/strategy.py` - `pressure_test()`'s fall-through no longer passes `br.success` through; always returns `success=False` with a defaulted error message
- `flowstate/tools/gsd_adapter.py` - one-line docstring edit, no code change
- `tests/test_tools.py` - extended `test_research_all_attempts_fail` to assert `success is False` and `error is not None`; added `test_research_partial_success_stays_true`, `test_strategy_empty_output_fails`, `test_strategy_bridge_failure_fails`

## Decisions Made
- Kept the report file written in both the all-failed and partial-success cases for research (it's a genuine failure record, not stub text) — matches plan instruction explicitly.
- Used a defaulted error string (`"strategy produced empty output"`) for the strategy empty-output case since `BridgeResult.error` is `None` when the bridge itself reports `success=True` with blank output — the adapter is the one that determined this is a failure, so it supplies the diagnostic.

## Deviations from Plan

None - plan executed exactly as written. `flowstate/tools/base.py`'s `bridge_to_result()` helper is left unused by `strategy.py` now but remains defined (still potentially used elsewhere / by future adapters) — not removed, since removing it was out of scope for this plan.

## Issues Encountered
- `uv run` (without `--frozen`) silently rewrote `uv.lock` with unrelated extras (`eval`/`semantic` transitive deps) on every invocation in this worktree. Switched to `uv run --frozen` for all verification commands to avoid committing an out-of-scope lockfile diff; `uv.lock` is untouched by this plan's commits.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- HON-03, HON-04, HON-06 complete. Combined with plan 12-01 (HON-01, HON-02, HON-05) this closes Phase 12's honesty scope — `_run_step` already routes `success=False` to BLOCKED, so no orchestrator changes were needed here.
- Full test suite: 950 passed, 91.95% coverage (gate is 80%).
- Ready for Phase 13's mechanism work (research measure/keep-discard loop, strategy scored rubric) to build on adapters that can now report failure honestly.

---
*Phase: 12-honesty-failure-capability*
*Completed: 2026-07-10*
## Self-Check: PASSED
