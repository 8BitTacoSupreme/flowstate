---
phase: 12-honesty-failure-capability
plan: 01
subsystem: infra
tags: [discipline, orchestrator, cli, honesty, ci]

# Dependency graph
requires: []
provides:
  - "check_setup() derives success from a required-set (git_repo AND pytest_config) instead of hardcoding True"
  - "Orchestrator Discipline step routed through _run_step (BLOCKED on failed audit, StepFailed emitted)"
  - "flowstate discipline CLI subcommand — non-zero exit on failed audit, zero on healthy repo"
affects: [12-02-honesty-failure-capability, 12-03-honesty-failure-capability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Required-set gating: success = all(checks[k] for k in required) — small explicit tuple, not a literal True"
    - "Step execute_fn wraps a non-ToolAdapter check (check_setup) into ToolResult so it reuses the shared _run_step BLOCKED/StepFailed machinery"

key-files:
  created: []
  modified:
    - flowstate/discipline.py
    - flowstate/orchestrator.py
    - flowstate/cli.py
    - tests/test_discipline.py
    - tests/test_orchestrator.py

key-decisions:
  - "Required-set is exactly git_repo AND pytest_config; the other five checks stay informational (reported in summary, never gate success)"
  - "Discipline execute_fn's error string names the specific failing required checks (e.g. 'required check(s) failed: git_repo')"
  - "flowstate discipline mirrors flowstate verify's exit-code shape (sys.exit(1) on failure) rather than verify's fixture-gate machinery — kept minimal like doctor"

patterns-established:
  - "Non-adapter pure-Python checks (like discipline) can be threaded through _run_step via a tiny execute_fn closure — no parallel BLOCKED/event logic needed"

requirements-completed: [HON-01, HON-02]

duration: 4min
completed: 2026-07-10
---

# Phase 12 Plan 01: Discipline Honesty Floor Summary

**`check_setup()` now derives success from a required-set (git_repo AND pytest_config) instead of hardcoding True; the orchestrator routes Discipline through the shared `_run_step` BLOCKED/StepFailed machinery; a new `flowstate discipline` CLI subcommand exits non-zero on a failed audit.**

## Performance

- **Duration:** 4 min (commit-to-commit)
- **Started:** 2026-07-10T12:47:17-04:00
- **Completed:** 2026-07-10T12:50:03-04:00
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- A repo missing `.git` or a pytest config now makes `check_setup().success` return `False` — the audit can fail for the first time since the module existed
- The orchestrator's Discipline step no longer bypasses the shared runner; a failed audit now sets the tool `BLOCKED`, emits `StepFailed`, and prints red (all via existing `_run_step`/`_print_summary` machinery — no new summary logic needed)
- `flowstate discipline` composes in CI alongside `doctor`/`verify`: exits `1` on an unhealthy repo, `0` on a healthy one
- Reconciled the two tests that encoded the old lie (`test_empty_dir` asserting success on a bare dir; two orchestrator all-COMPLETED loops that never set up a real repo) and added required-set contract tests plus a `BLOCKED`-path test

## Task Commits

Each task was committed atomically:

1. **Task 1: Derive discipline success from a required-set (HON-01)** - `8b3e79e` (feat)
2. **Task 2: Route Discipline through _run_step and add the flowstate discipline CLI (HON-02)** - `cb730db` (feat)
3. **Task 3: Reconcile tests that encode the old lie and add failure-path tests** - `0b04b6a` (test)

## Files Created/Modified
- `flowstate/discipline.py` - `check_setup` computes `success = all(checks[k] for k in ("git_repo", "pytest_config"))` instead of hardcoding `True`; `checks` dict and `summary` string unchanged
- `flowstate/orchestrator.py` - Discipline step now calls `_run_step("discipline", 5, 5, execute_fn, bus=bus)` with an `execute_fn` that wraps `check_setup(root)` into a `ToolResult(success=audit.success, output=audit.summary, error=...)`; deleted the unconditional `update_tool(..., COMPLETED)` bypass; added `ToolResult` import
- `flowstate/cli.py` - added `@main.command("discipline")` mirroring `verify`'s exit-code shape: prints the audit summary (green/red), `sys.exit(1)` on failure
- `tests/test_discipline.py` - flipped `test_empty_dir` to `assert not result.success`; added `test_required_set_git_only_fails` and `test_required_set_both_present_succeeds`
- `tests/test_orchestrator.py` - gave `test_dry_run_pipeline` and `test_run_pipeline_harvest_failure_does_not_abort` a healthy repo (`.git` + `pyproject.toml`) before `run_pipeline`; added `test_discipline_blocks_on_unhealthy_repo`

## Decisions Made
- Required-set kept to exactly two keys (`git_repo`, `pytest_config`) per the locked HON-01 decision — hooks/tests-dir/src-dir/planning-dir stay advisory, reported but never gating
- Discipline's `execute_fn` error message names the specific failing required check(s) rather than a generic string, so `_run_step`'s red output and `ToolState.error` are actionable
- `flowstate discipline` does not add journaling/gotcha capture (that's `verify`-specific); kept minimal like `doctor`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- `uv sync` (run to make `ruff`/`pytest` available in the worktree venv) modified `uv.lock` with unrelated resolver metadata (`annotated-doc` etc.) as a side effect of dependency resolution. This is out of scope for HON-01/02 and was left unstaged/uncommitted — not part of any task commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- HON-01 and HON-02 are complete: the Discipline audit can fail and the failure is surfaced through the orchestrator and a new CI-composable CLI command
- Full suite: 950 passed, 91.81% coverage (≥80% gate)
- `tests/test_orchestrator_extended.py` was not touched (owned by plan 12-03) — no conflict expected
- Plans 12-02/12-03 (HON-03..06) can proceed independently; no shared state beyond the now-honest `discipline.py`/`orchestrator.py` surface

---
*Phase: 12-honesty-failure-capability*
*Completed: 2026-07-10*
