---
phase: 03-ingredients-pack-canon-fixtures
plan: "01"
subsystem: pack
tags: [repomix, cli, subprocess, install-manifest, state-migration]
dependency_graph:
  requires: []
  provides: [flowstate/pack.py, flowstate pack CLI command, InstallEntry kind=pack+fixture, _make_bridge mcp__repomix]
  affects: [flowstate/state.py, flowstate/cli.py, flowstate/orchestrator.py]
tech_stack:
  added: [flowstate/pack.py]
  patterns: [locator-then-subprocess, PackResult/PackConfig dataclass mirroring BridgeResult/BridgeConfig, _register manifest helper reuse]
key_files:
  created:
    - flowstate/pack.py
    - tests/test_pack.py
  modified:
    - flowstate/state.py
    - flowstate/cli.py
    - flowstate/orchestrator.py
    - tests/test_install_manifest.py
    - tests/test_orchestrator.py
    - tests/test_state.py
decisions:
  - "_find_repomix mirrors _find_claude: FLOWSTATE_REPOMIX_BIN env var > PATH shutil.which > candidate paths"
  - "run_pack imports _register from context.py at call-time (lazy) to avoid circular import at module level"
  - "is_pack_stale uses entry.created_at.timestamp() vs max(*.py mtime); no py files = not stale"
  - "_make_bridge passes allowed_tools=['mcp__repomix'] as a kwarg alongside project_root, not as a BridgeConfig default — single construction site, explicit override"
  - "v0.3.0->v0.4.0 migration guard fixed from '>= 0.3.0' to '>= 0.4.0' so 0.3.0 state flows into migration ladder"
  - "Existing test_state.py + test_install_manifest.py assertions updated to reflect final version 0.4.0 (Rule 1 fix)"
metrics:
  duration: "9m"
  completed_date: "2026-06-06"
  tasks_completed: 3
  files_changed: 7
---

# Phase 03 Plan 01: Repomix Pack Ingredient Summary

**One-liner:** Repomix pack service with locator, staleness repack, manifest registration, flowstate pack CLI, and mcp__repomix allowed-tools passthrough in _make_bridge.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Extend InstallEntry.kind Literal with pack+fixture; bump version to 0.4.0; fix migration guard | 477a4ea |
| 2 | Create flowstate/pack.py — _find_repomix, run_pack, is_pack_stale, PackResult, PackConfig | 6663a24 |
| 3 | Add flowstate pack CLI command; set allowed_tools=["mcp__repomix"] in _make_bridge | 2eb0f36 |

## What Was Built

**flowstate/pack.py** — new service module mirroring bridge.py structure:
- `_find_repomix()`: locator with FLOWSTATE_REPOMIX_BIN env var override, PATH search, 3 candidate paths
- `PackResult` / `PackConfig` dataclasses mirroring BridgeResult / BridgeConfig (with `__post_init__` calling the locator)
- `run_pack(root, *, compress=False)`: builds repomix argv, runs subprocess with timeout/error handling, registers kind="pack" entry on install_manifest via `_register` helper from context.py
- `is_pack_stale(root, state)`: compares max *.py mtime against pack entry's created_at; returns True when no entry

**flowstate/state.py** changes:
- `InstallEntry.kind` Literal extended from 5 to 7 values: adds "pack" and "fixture"
- `FlowStateModel.version` default bumped to "0.4.0"
- `_migrate_state` early-exit guard fixed from `>= "0.3.0"` to `>= "0.4.0"` (critical — old guard short-circuited v0.3.0->v0.4.0 migration)
- v0.3.0->v0.4.0 migration block added (no-op on entries; bumps version string)

**flowstate/cli.py** — new `flowstate pack` command:
- Options: `--root`, `--compress`, `--force`
- Up-to-date check: loads state, skips if pack entry exists and `is_pack_stale` returns False (unless --force)
- Success: prints `[green]Pack written:[/green] <relative path>`
- Failure: prints the error, calls `sys.exit(1)` (non-zero exit when repomix absent)

**flowstate/orchestrator.py** — `_make_bridge` passes `allowed_tools=["mcp__repomix"]` on every BridgeConfig construction, so every spawned `claude --print` agent inherits the repomix-MCP grant.

## Test Coverage

- `tests/test_pack.py`: 17 new tests covering TestFindRepomix (4), TestRunPack (5), TestIsPackStale (4), TestPackCommand (4). Fake repomix shell script + FLOWSTATE_REPOMIX_BIN monkeypatch — never shells out to real repomix.
- `tests/test_install_manifest.py`: updated for pack+fixture kinds, v0.4.0 default, new test_migrate_v030_to_v040
- `tests/test_orchestrator.py`: new TestMakeBridgeAllowedTools class (2 tests) asserting bridge.config.allowed_tools contains "mcp__repomix"
- `tests/test_state.py`: 4 migration assertions updated to reflect final version 0.4.0 (Rule 1 fix — pre-existing tests that tested correct old behavior)

Full suite result: **317 passed, 91.57% coverage** (≥80% gate passed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_state.py migration assertions expected "0.3.0" as final version**
- **Found during:** Task 1 GREEN phase
- **Issue:** 4 existing tests in test_state.py asserted migrated state version == "0.3.0" — correct before v0.4.0 migration, wrong after
- **Fix:** Updated all 4 assertions to expect "0.4.0" and renamed test_chained_migration_v010_to_v030 to test_chained_migration_v010_to_v040
- **Files modified:** tests/test_state.py
- **Commit:** 477a4ea

**2. [Rule 1 - Bug] test_install_manifest.py::test_migrate_v020_adds_empty_manifest expected "0.3.0"**
- **Found during:** Task 1 GREEN phase
- **Issue:** test_migrate_v020_adds_empty_manifest asserted version == "0.3.0" after migrating v0.2.0 — same issue as above
- **Fix:** Updated assertion and docstring to reflect "0.4.0"
- **Files modified:** tests/test_install_manifest.py
- **Commit:** 477a4ea

**3. [Rule 1 - Bug] test_pack.py::test_fresh_pack_not_stale timing race**
- **Found during:** Task 2 test run
- **Issue:** The test wrote a .py file, then compared mtime to a datetime.now()-5s pack entry; on fast systems the file mtime == "now" and is newer than now-5s, making the pack appear stale when it should appear fresh
- **Fix:** Used `os.utime()` to back-date the source file by 30s so the comparison is deterministic
- **Files modified:** tests/test_pack.py

**4. [Rule 1 - Bug] CliRunner `mix_stderr=False` not supported by installed Click version**
- **Found during:** Task 2 CLI test run
- **Issue:** Click in this project doesn't expose `mix_stderr` on CliRunner.__init__
- **Fix:** Removed `mix_stderr=False` from all CliRunner() calls
- **Files modified:** tests/test_pack.py

**5. [Rule 1 - Bug] Ruff SIM102: nested `if` in pack command**
- **Found during:** Task 3 pre-commit hook
- **Issue:** `if not force and has_pack_entry: if not is_pack_stale:` is two nested ifs
- **Fix:** Extracted `has_pack_entry` boolean and merged into single `if not force and has_pack_entry and not is_pack_stale(root, state):`
- **Files modified:** flowstate/cli.py

## Self-Check: PASSED

Files created/exist:
- [x] /Users/jhogan/frameworx/flowstate/pack.py
- [x] /Users/jhogan/frameworx/tests/test_pack.py
- [x] /Users/jhogan/frameworx/.planning/phases/03-ingredients-pack-canon-fixtures/03-01-SUMMARY.md

Commits exist:
- [x] 477a4ea — Task 1
- [x] 6663a24 — Task 2
- [x] 2eb0f36 — Task 3
