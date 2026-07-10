---
phase: 13-adapters-earn-their-names
plan: 03
subsystem: discipline
status: complete
tags: [MECH-03, discipline-adapter, superpowers, red-green-gate, dry-run]
requires:
  - "flowstate/discipline.py::check_setup / AuditResult"
  - "flowstate/orchestrator.py::run_pipeline (dry_run in scope)"
  - "flowstate/tools/base.py::run_cmd (subprocess+dry-run MOCK precedent)"
provides:
  - "Gating live discipline audit: runs the project's tests as a required-set member"
  - "_read_git_state / _run_project_tests / _check_hook_contents (pure Python + subprocess)"
  - "AuditResult.required — orchestrator derives the BLOCKED error from the real failing member"
  - "Dry-run zero-spawn guard: check_setup(root, dry_run=True) spawns no subprocess"
affects:
  - "flowstate/discipline.py"
  - "flowstate/orchestrator.py"
  - "tests/test_discipline.py"
tech-stack:
  added: []
  patterns:
    - "argv-LIST subprocess only (never shell=True / no string interpolation of branch/path)"
    - "tri-state test-run (True/False/None) with None-degrade on FileNotFound/timeout"
    - "dry-run short-circuits BEFORE any subprocess.run (MOCK precedent from run_cmd)"
    - "hook CONTENTS inspection (is_file + size>0 + os.X_OK) — never execute the hook"
key-files:
  created: []
  modified:
    - "flowstate/discipline.py"
    - "flowstate/orchestrator.py"
    - "tests/test_discipline.py"
decisions:
  - "tests_pass is a GATING required-set member on live runs (_REQUIRED_LIVE); tests_pass is False (suite failed) OR None (absent/timeout/unrunnable) both fail the audit — no fake pass"
  - "Dry-run required-set is _REQUIRED_DRYRUN=(git_repo, pytest_config); tests_pass stays in checks for shape but is non-gating and reported-only"
  - "_TEST_TIMEOUT=900s (generous so a healthy real suite is never spuriously failed); a timeout still degrades to None -> audit fails (honest, never a hang)"
  - "git rev-list --left-right --count @{u}...HEAD: parts[0]=behind (@{u}), parts[1]=ahead (HEAD); no upstream -> command fails -> both stay None"
  - "Existing path-only TestCheckSetup tests converted to dry_run=True (Rule 3 deviation) so each commit stays green under the new live gate and spawns no nested pytest"
metrics:
  duration: ~20 min
  completed: 2026-07-10
---

# Phase 13 Plan 03: Gating Live Discipline Audit Summary

The discipline adapter now earns the Superpowers name: on a LIVE run it actually runs the
project's tests (a GATING required-set member), reads real git state (branch / dirty /
ahead-behind), and inspects the pre-commit hook's contents (non-empty + executable, never
executed) — pure Python + `subprocess` with argv lists, no new deps, no shell injection.
Under `--dry-run` the step spawns ZERO subprocesses and reports tests/git as skipped,
preserving the pre-Phase-13 side-effect profile.

## What Was Built

**Task 1 — `flowstate/discipline.py` + `flowstate/orchestrator.py` (commit `71f3d92`)**
- Added `_read_git_state(root)` — real branch/dirty/ahead-behind via three argv-list git
  calls; any failure (no git, not a repo, no upstream) degrades to None/False, never raises.
- Added `_run_project_tests(root)` — `["python","-m","pytest","-q"]`, `timeout=_TEST_TIMEOUT`
  (900s); True on exit 0, False on any other exit (incl. pytest exit 5 "no tests collected"),
  None only on FileNotFoundError/TimeoutExpired.
- Added `_check_hook_contents(root)` — `.git/hooks/pre-commit` `is_file()` AND `st_size > 0`
  AND `os.access(..., os.X_OK)`; never executes the hook.
- `check_setup(root, *, dry_run=False)` now branches: live path gates `success` on
  `_REQUIRED_LIVE=(git_repo, pytest_config, tests_pass)` and renders git/test summary lines;
  dry-run path derives `success` from `_REQUIRED_DRYRUN=(git_repo, pytest_config)` with zero
  spawns and `Tests: skipped (dry-run)` / `Git state: skipped (dry-run)` lines.
- `AuditResult` gained a `required: tuple[str, ...]` field (defaulted to `_REQUIRED_LIVE`).
- `git_hooks` check upgraded from `Path.exists()` to `_check_hook_contents` (no spawn, both paths).
- Orchestrator `_run_discipline` now calls `check_setup(root, dry_run=dry_run)` and derives the
  BLOCKED error from `audit.required` (the hardcoded `("git_repo","pytest_config")` tuple is gone),
  so a suite-only failure is named honestly (`required check(s) failed: tests_pass`).
- `flowstate/cli.py` left untouched — `flowstate discipline` stays an explicit LIVE audit.

**Task 2 — `tests/test_discipline.py` (commit `e49db23`)**
- `TestReadGitState` (real temp repo, skipped if git absent): branch/clean/dirty/untracked/no-upstream/non-repo.
- `TestRunProjectTests`: tri-state via monkeypatched `discipline.subprocess.run`
  (0→True, non-zero→False, exit 5→False, FileNotFound→None, TimeoutExpired→None). No recursive pytest.
- `TestLiveGating`: passing suite→success, failing→fail, absent(None)→fail; git-real + pytest-stubbed
  via argv router; summary `branch`/`Tests: passed|failed|not run` lines asserted.
- `TestDryRunZeroSpawn`: `Mock(side_effect=AssertionError)` proves `subprocess.run.call_count == 0`
  under `dry_run=True`, `success` from `_REQUIRED_DRYRUN`, skipped summary lines present.
- `TestCheckHookContents`: executable/empty/non-executable/absent.

## Deviations from Plan

**1. [Rule 3 - Blocking] Existing path-only tests converted to `dry_run=True` inside Task 1**
- **Found during:** Task 1 (pre-commit gate runs the full suite with `--cov-fail-under=80`).
- **Issue:** The new live gate makes `check_setup(tmp_path)` spawn a real `python -m pytest`
  and gate on `tests_pass`; two success-asserting tests (`test_full_project`,
  `test_required_set_both_present_succeeds`) would fail and every live-path test would spawn a
  nested pytest, violating the plan's "do not let the discipline test-run recurse" constraint.
- **Fix:** Converted the existing path-only `TestCheckSetup` cases (which probe checks identical
  on both paths) to `dry_run=True`, and made `test_full_project`'s hook real (chmod 0o755) so it
  passes the upgraded `git_hooks` content check. This kept each atomic commit green.
- **Files modified:** `tests/test_discipline.py` (in the Task 1 commit).
- **Commit:** `71f3d92`.
- **Note:** The plan assigned all test edits to Task 2; the pre-commit gate forced the minimal
  green-keeping edits to land with the code change that broke them. Comprehensive new behavioral
  tests still landed in Task 2 (`e49db23`) as planned.

**2. [Rule 3 - Blocking] Docstring reworded to satisfy `grep shell=True`**
- The acceptance criterion `grep -n "shell=True" flowstate/discipline.py` must return no matches;
  a docstring said "never shell=True". Reworded to "never a shell string" — same meaning, clean grep.

## Threat Model Coverage

All `mitigate` dispositions from the plan's STRIDE register are implemented and test-covered:
T-13-06 (argv lists only, no shell), T-13-07 (hook stat/read only, never executed),
T-13-08 (bounded `_TEST_TIMEOUT`; dry-run skips entirely), T-13-09 (missing runner → None → honest
fail), T-13-10 (dry-run zero-spawn asserted via `call_count == 0`). No package installs (T-13-SC accept).

## Verification

- `python -m pytest tests/test_discipline.py -q` → 27 passed.
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` → 985 passed, 92.07% coverage.
- `grep -n "shell=True" flowstate/discipline.py` → no matches.
- `grep -n "check_setup(root, dry_run=dry_run)" flowstate/orchestrator.py` → line 315.
- `_run_discipline` no longer hardcodes `("git_repo","pytest_config")`; derives from `audit.required`.
- `git diff --name-only` for the plan → only `flowstate/discipline.py`, `flowstate/orchestrator.py`,
  `tests/test_discipline.py`; `flowstate/cli.py` untouched.

## Self-Check: PASSED

- FOUND: flowstate/discipline.py (contains `_read_git_state`, `_run_project_tests`, `_check_hook_contents`)
- FOUND: commit 71f3d92 (Task 1)
- FOUND: commit e49db23 (Task 2)
