---
phase: 08-runnable-verification
plan: "03"
status: complete
subsystem: cli
tags: [verify, cli, gotchas, journal, loop-wiring]
dependency_graph:
  requires: ["08-01", "08-02"]
  provides: ["flowstate verify command", "VER-01 report/exit", "VER-02 loop closure"]
  affects: [flowstate/cli.py, tests/test_cli.py]
tech_stack:
  added: []
  patterns:
    - "doctor-command clone: resolve_root + load_state + run_verify + best-effort MemoryStore block"
    - "sys.exit(fails) exit-code contract for CI/pre-commit composition"
    - "CliRunner + MemoryStore assertions for loop-closure test coverage"
key_files:
  modified:
    - flowstate/cli.py
    - tests/test_cli.py
decisions:
  - "Placed verify command between doctor and repair in cli.py to mirror the diagnostic-command grouping"
  - "Loop-closure block opens one MemoryStore context for both capture_gotcha (per FAIL) and append_verify_entry (every run)"
  - "no-fixtures guard checks fixtures_dir.exists() AND any(glob) so an empty dir also exits 0"
metrics:
  duration_minutes: 20
  completed: "2026-06-09T14:40:00Z"
  tasks_completed: 2
  files_modified: 2
---

# Phase 08 Plan 03: flowstate verify CLI command Summary

`flowstate verify` command added to cli.py — Rich PASS/FAIL/SKIP report from `run_verify`, exits non-zero (count of FAILs) for CI/pre-commit, captures gotcha per FAIL and appends a verify journal entry every run, closing the compounding loop.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | flowstate verify @main.command in flowstate/cli.py | dd7fbcb | flowstate/cli.py |
| 2 | tests/test_cli.py — flowstate verify CLI cases | 660ca67 | tests/test_cli.py |

## What Was Built

### Task 1 — `flowstate verify` command (flowstate/cli.py)

Added `@main.command("verify")` with `--root` option, cloning the doctor command structure:

- `resolve_root + _root_was_explicit()` → same root resolution as all other commands
- Early no-fixtures guard: if `.planning/fixtures/` absent or empty → print "No fixtures to verify" and `return` (exit 0)
- `load_state(root)` + `run_verify(state, root)` → `list[VerifyResult]`
- Best-effort loop-closure block (try/except Exception: pass): opens one `MemoryStore`, calls `capture_gotcha(source="verify", severity="error")` for each FAIL result, then calls `append_verify_entry` unconditionally
- Rich `Table` with columns Gate/Status/Fixture/Message; `status_style = {"pass": "green", "fail": "red", "skip": "dim"}`
- Summary line: `{fails} fail(s), {passes} pass(es), {skips} skip(s)`
- `sys.exit(fails)` when fails > 0; otherwise falls through to implicit exit 0

### Task 2 — CLI tests (tests/test_cli.py)

Added `_make_verify_install()` helper and `TestVerifyCommand` class with 7 tests:

- `test_verify_empty_project_exits_zero`: no fixtures dir → exit 0, "no fixtures" in output
- `test_verify_all_pass_or_skip_exits_zero`: healthy install with starter fixture → exit 0
- `test_verify_missing_artifact_exits_nonzero`: missing manifest artifact → exit > 0, "fail" in output
- `test_verify_fail_captures_gotcha`: FAIL run → `MemoryKind.INSIGHT` entry with `source="verify"` in memory.db
- `test_verify_run_appends_journal_entry`: any run → `MemoryKind.RUN` entry tagged "verify" in memory.db
- `test_verify_malformed_fixture_no_crash`: broken JSON fixture → int exit code, no traceback
- `test_verify_help_lists_command`: `--help` exits 0

## Verification Results

- `python -m pytest tests/test_cli.py -q -k verify`: 7 passed, 0 failed
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q`: 545 passed, 92.24% coverage
- `ruff check flowstate/cli.py tests/test_cli.py`: all checks passed
- `ruff format --check flowstate/cli.py tests/test_cli.py`: already formatted
- Smoke test: `flowstate verify --root <empty-tmp>` exits 0 with "no fixtures" message
- `grep -c "import.*bridge" flowstate/cli.py` = 0 (no bridge/LLM seam added)

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. The verify command
reads only local files and writes only to local memory.db, matching the threat model's documented
surface (T-08-10 through T-08-SC all addressed per plan).

## Self-Check: PASSED

- flowstate/cli.py contains `def verify` — FOUND
- tests/test_cli.py contains `TestVerifyCommand` — FOUND
- Commit dd7fbcb exists — FOUND
- Commit 660ca67 exists — FOUND
