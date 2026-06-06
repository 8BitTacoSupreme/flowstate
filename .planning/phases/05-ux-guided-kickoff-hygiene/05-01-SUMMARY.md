---
phase: 05-ux-guided-kickoff-hygiene
plan: "01"
subsystem: cli
tags: [click, interview, state, pydantic, scaffold, kickoff, tdd]
status: complete

# Dependency graph
requires:
  - phase: 04-pack-context-prefix-fixtures
    provides: write_context_files (fixture + .mcp.json), run_pack (PackResult + graceful degradation)
  - phase: 03-codebase-map-fixtures-mcp
    provides: context file scaffolding, install_manifest tracking

provides:
  - "flowstate kickoff command — scaffold-only entry point (no LLM pipeline)"
  - "InterviewAnswers.deployment_target field persisted to state"
  - "run_interview test_coverage validation (0-100 range re-prompt)"
  - "run_interview deployment_target branching (only asked when architecture_pattern non-empty)"

affects: [05-02-docs, future-phases-using-kickoff, any-phase-running-run_interview]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scaffold-only CLI command pattern (no bridge/LLM, just context + pack)"
    - "KICK-02 branching: field shown only when prerequisite field is non-empty"
    - "KICK-02 validation: IntPrompt looped until value in range"

key-files:
  created:
    - "tests/test_interview.py (extended — 9 new KICK-02 tests)"
  modified:
    - "flowstate/state.py (InterviewAnswers.deployment_target added)"
    - "flowstate/interview.py (SECTIONS + branching + validation)"
    - "flowstate/cli.py (kickoff command)"
    - "tests/test_cli.py (TestKickoffCommand — 6 new tests)"

key-decisions:
  - "kickoff imports write_context_files + run_pack locally (never imports run_pipeline)"
  - "branching evaluated at prompt-time against the current in-memory answers.architecture_pattern value"
  - "pack failure in kickoff is a warning (yellow), not an error — kickoff exits 0 regardless"
  - "deployment_target placed in discipline SECTIONS so init and kickoff share it with zero divergence"

patterns-established:
  - "Scaffold-only command: load_state → interview → write_context_files → run_pack → save_state"
  - "Shared run_interview: both init and kickoff call the same function — new questions appear in both"

requirements-completed: [KICK-01, KICK-02]

# Metrics
duration: 6min
completed: 2026-06-06
---

# Phase 5 Plan 01: Guided Kickoff + Interview Enhancements Summary

**scaffold-only `flowstate kickoff` command with shared interview branching/validation and `deployment_target` field persisted via InterviewAnswers**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-06T18:50:08Z
- **Completed:** 2026-06-06T18:56:22Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added `flowstate kickoff` — runs interview, writes context files, calls run_pack, saves state, never touches run_pipeline
- Added `deployment_target: str = ""` to InterviewAnswers; field round-trips through save/load
- KICK-02 validation: `test_coverage` re-prompts until value is 0-100
- KICK-02 branching: `deployment_target` is only asked when `architecture_pattern` is non-empty
- 15 new tests covering all specified behaviors; full suite at 381 tests, 92.85% coverage

## Task Commits

Each task was committed atomically:

1. **Task 1: Add kickoff interview field(s) to InterviewAnswers and enhance shared run_interview** - `55fa7a2` (feat)
2. **Task 2: Add the scaffold-only `flowstate kickoff` command** - `772ab24` (feat)

_Note: Both tasks followed TDD (RED failing tests committed before GREEN implementation)._

## Files Created/Modified
- `flowstate/state.py` - Added `deployment_target: str = ""` to InterviewAnswers
- `flowstate/interview.py` - Added deployment_target to SECTIONS, test_coverage validation loop, branching guard
- `flowstate/cli.py` - New `kickoff` command (--root, --skip-interview only; no pipeline flags)
- `tests/test_interview.py` - 9 new tests for deployment_target field, round-trip, SECTIONS presence, validation, branching
- `tests/test_cli.py` - 6 new TestKickoffCommand tests

## Decisions Made
- `kickoff` uses local imports and never imports `run_pipeline` — import-level enforcement of KICK-01
- Branching evaluated against `answers.architecture_pattern` at prompt-time (the live in-memory value set during the interview), not a pre-interview snapshot
- Pack failure in `kickoff` surfaces as a `[yellow]Pack skipped:[/yellow]` line; exit code stays 0 — consistent with Phase 3/4 graceful degradation contract
- `deployment_target` placed after `architecture_pattern` in the discipline SECTIONS entry so the branching check has the correct prerequisite value in scope

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fix: branching test needed to answer architecture_pattern during interview**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_deployment_target_asked_when_architecture_pattern_set` set `state.interview.architecture_pattern = "hexagonal"` before calling `run_interview`, but the mock returned `""` for all prompts, clearing the field before the branching check ran
- **Fix:** Updated the fake_prompt function to return `"hexagonal"` when the question contains "architectural pattern" — simulating a user who answers with a non-empty pattern
- **Files modified:** tests/test_interview.py
- **Verification:** Test passes; branching logic confirmed correct
- **Committed in:** 55fa7a2 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test correctness)
**Impact on plan:** Required to correctly validate the branching invariant. No scope creep.

## Issues Encountered
- Pre-existing ruff errors in `tests/test_doctor.py` (B017) and `tests/test_repair.py` (F401) — out of scope per surgical change rule; logged here for awareness but not fixed.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `flowstate kickoff` is fully operational and test-covered
- The shared `run_interview` now includes deployment_target + validation + branching
- Phase 05-02 (DX-01 SUMMARY frontmatter hygiene) is independent and can proceed immediately

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/05-ux-guided-kickoff-hygiene/05-01-SUMMARY.md`
- Commit `55fa7a2` exists (Task 1: deployment_target + run_interview enhancements)
- Commit `772ab24` exists (Task 2: kickoff command)
- All source files present: `flowstate/state.py`, `flowstate/interview.py`, `flowstate/cli.py`
- All test files present: `tests/test_interview.py`, `tests/test_cli.py`

---
*Phase: 05-ux-guided-kickoff-hygiene*
*Completed: 2026-06-06*
