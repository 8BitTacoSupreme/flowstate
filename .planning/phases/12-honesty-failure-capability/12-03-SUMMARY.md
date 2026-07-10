---
phase: 12-honesty-failure-capability
plan: 03
subsystem: orchestrator
tags: [honesty, failure-capability, pipeline, testing]
status: complete

requires:
  - phase: 12-honesty-failure-capability
    provides: "12-01 Discipline routed through _run_step; 12-02 research/strategy adapters return success=False on failure"
provides:
  - "Live (non-dry-run) run with no locatable claude CLI no longer silently swaps to a stub dry-run bridge"
  - "Bridge-dependent steps (research, strategy) BLOCK loudly instead of faking success"
affects: [orchestrator, cli-run-status]

tech-stack:
  added: []
  patterns:
    - "Live bridge passed through unmodified even when unavailable; success=False propagates naturally through existing _run_step machinery"

key-files:
  created: []
  modified:
    - flowstate/orchestrator.py
    - tests/test_orchestrator_extended.py

key-decisions:
  - "Deleted the silent bridge=ClaudeBridge(..., dry_run=True) reassignment rather than adding a new guard — relies entirely on existing success/BLOCKED machinery in _run_step, no per-step special-casing"
  - "mode_tag changed to '(no claude CLI — bridge steps will be blocked)' to honestly communicate the live-no-CLI state instead of claiming a fallback"
  - "Genuine --dry-run path (state.preferences.dry_run=True) deliberately untouched — locked by a new test"

patterns-established:
  - "Fail-loud honesty: adapters/bridge already returned success=False on unavailability (from 12-02); the orchestrator no longer masks that signal with a stub swap"

requirements-completed: [HON-05]

duration: 15min
completed: 2026-07-10
---

# Phase 12 Plan 03: Remove silent live-no-CLI dry-run swap Summary

**Deleted the silent bridge-to-dry-run-stub swap in `run_pipeline`; a live run with no locatable `claude` CLI now BLOCKs research/strategy via the existing success=False → BLOCKED machinery instead of faking success with `[dry-run]` stub text.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-10T16:40:00Z
- **Completed:** 2026-07-10T16:57:58Z
- **Tasks:** 3/3 completed (Task 3 was verification-only, no code changes required)
- **Files modified:** 2

## Accomplishments
- Closed the last of the three success-on-failure paths identified in the phase (HON-05)
- Live-no-CLI runs now report `Pipeline finished: N/M succeeded, K blocked.` instead of `All steps succeeded.`
- No `[dry-run] claude prompt` stub text is ever written to `report.md`/`strategy.md` on a live run
- Genuine `--dry-run` behavior verified unchanged via a new locking test
- Full suite (954 tests) passes at 91.96% coverage, well above the 80% gate

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove the silent dry-run swap; fail loud on live-no-CLI (HON-05)** - `9b2f7e5` (fix)
2. **Task 2: Rewrite the fall-back test to assert fail-loud behavior (HON-05)** - `d22cffe` (test)
3. **Task 3: Full-suite + coverage gate** - verification only, no code changes needed (coverage already at 91.96%, ruff already clean)

## Files Created/Modified
- `flowstate/orchestrator.py` - Removed `bridge = ClaudeBridge(config=bridge.config, dry_run=True)` reassignment in `run_pipeline`; updated the red `mode_tag` text to honestly describe the blocked state instead of claiming a fallback
- `tests/test_orchestrator_extended.py` - Replaced `test_pipeline_no_bridge_falls_back` (which asserted the old lie) with `test_pipeline_live_no_cli_blocks_loud` (monkeypatches `flowstate.bridge._find_claude` to `""`, asserts research/strategy BLOCKED and no stub text written) and added `test_pipeline_dry_run_still_succeeds` (locks the genuine `--dry-run` path: all tools COMPLETED, MOCK report content present)

## Deviations from Plan

None - plan executed exactly as written. Task 3 required no code changes: the full suite was already green with 91.96% coverage (comfortably above the 80% gate) and `ruff check`/`ruff format --check` were already clean after Tasks 1-2.

## Verification

- `grep -c "falling back to dry-run" flowstate/orchestrator.py` → `0`
- `python -m pytest tests/test_orchestrator_extended.py -q` → 6 passed
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` → 954 passed, 91.96% coverage
- `ruff check flowstate/ tests/` → All checks passed
- `ruff format --check flowstate/orchestrator.py` → 1 file already formatted

## Self-Check: PASSED

- FOUND: flowstate/orchestrator.py (modified, swap removed)
- FOUND: tests/test_orchestrator_extended.py (modified, new tests present)
- FOUND: commit 9b2f7e5 (Task 1)
- FOUND: commit d22cffe (Task 2)
