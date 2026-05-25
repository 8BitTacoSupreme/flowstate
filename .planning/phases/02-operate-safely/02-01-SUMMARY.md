---
phase: 02-operate-safely
plan: 01
subsystem: state-management
tags: [pydantic, install-manifest, sqlite, fresh, sha256, migration]

# Dependency graph
requires:
  - phase: 01-pivot
    provides: clean v0.3.0 baseline with FlowStateModel, MemoryStore, write_context_files, fresh command
provides:
  - InstallEntry Pydantic model on FlowStateModel
  - install_manifest field tracking every file FlowState writes (path, owner, kind, created_at, checksum)
  - Backfill migration from pre-manifest (v0.2.0) flowstate.json by scanning .planning/, .claude/, research/, memory.db
  - Manifest-driven `flowstate fresh` (replaces destructive _FRESH_TARGETS blind delete)
  - --force flag to remove orphans (files in .planning//research/ not in manifest)
  - sha256 checksum drift detection (warns "modified" when on-disk hash differs from recorded)
  - Empty-directory safety: fresh on a brand-new project no longer raises FileNotFoundError
affects: [02-02-doctor, 02-03-status, 02-04-hooks]

tech-stack:
  added: []  # No new runtime deps — uses hashlib, typing.Literal from stdlib
  patterns:
    - "Register-on-write: every file-creating function appends an InstallEntry as it writes"
    - "Idempotent manifest mutation: same-path entries are replaced, not duplicated"
    - "Owner-tagged manifest: 'context' for write_context_files, 'memory' for memory.db, '<tool_name>' for adapter artifacts"
    - "Backfill on migration: when bumping schema, synthesize manifest from disk so existing projects don't lose ownership data"

key-files:
  created:
    - tests/test_install_manifest.py
  modified:
    - flowstate/state.py
    - flowstate/context.py
    - flowstate/orchestrator.py
    - flowstate/cli.py
    - tests/test_state.py
    - tests/test_context.py
    - tests/test_orchestrator.py
    - tests/test_cli.py

key-decisions:
  - "InstallEntry uses Literal[...] for kind to get Pydantic ValidationError on typos instead of silent acceptance"
  - "checksum=None semantically means 'mutable file' (memory.db) — _verify_checksum returns True for None"
  - "Backfill runs only when migrating to v0.3.0 with empty install_manifest AND root is not None (avoids surprise scans on schema-default loads)"
  - "Orphan scan is bounded to .planning/, research/, memory.db, flowstate.json — does NOT touch .claude/ or source code (Rule 2 safety)"
  - "Removed legacy CONTEXT.md from cleanup targets — it's v1 cruft, never written by current pipeline"
  - "Sweep empty subdirectories after deletion so .planning/research/ doesn't linger after orphan removal"

patterns-established:
  - "Manifest-aware destructive commands: any future destructive op (DOCT-02 repair) should consult install_manifest, not hardcoded paths"
  - "checksum=None convention for mutable artifacts: extends to any future mutable file (logs, caches, indexes)"

requirements-completed: [INST-01, INST-02, INST-03]

# Metrics
duration: ~12min
completed: 2026-05-25
---

# Phase 2 Plan 1: Install Manifest Tracking Summary

**FlowState now records every file it writes on `install_manifest`, and `flowstate fresh` consults that record instead of blind-deleting a hardcoded target list — orphans are reported, not nuked.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-25T19:04:23Z
- **Completed:** 2026-05-25T19:16Z
- **Tasks:** 3 / 3
- **Files modified:** 8 (4 source, 4 tests)
- **Test count:** 223 passing (up from 196 before this plan)
- **Coverage:** 90.76% (well above 80% floor)

## Accomplishments

- **INST-01 — Manifest schema landed:** `InstallEntry` Pydantic model with `path`, `owner`, `kind: Literal[5]`, `created_at`, `checksum` lives on `FlowStateModel.install_manifest`. State version bumped 0.2.0 → 0.3.0. `_migrate_state` now chains v0.1.0 → v0.2.0 → v0.3.0 in one pass.
- **INST-02 — Init populates manifest:** `write_context_files` registers 5 entries (PROJECT.md, ROADMAP.md, config.json, CLAUDE.md, brief.md) with sha256 checksums. `run_pipeline` registers `memory.db` at MemoryStore creation (idempotent, checksum=None). `_run_step` registers each tool-adapter artifact via `_register_tool_artifact`.
- **INST-03 — Fresh consults manifest:** `_FRESH_TARGETS` deleted. New `_scan_orphans` finds files in `.planning/` / `research/` / `memory.db` / `flowstate.json` not in the manifest. New `_verify_checksum` flags drift with a "(modified)" warning. New `--force` flag removes orphans. Empty-directory case guards `state_path.exists()` before calling `load_state` (which has no `missing_ok` kwarg).
- **Backfill migration:** Loading a pre-manifest v0.2.0 flowstate.json on a project with existing `.planning/PROJECT.md` populates the manifest from disk on first read — existing projects upgrade without losing ownership data.

## Task Commits

Each task followed strict TDD: failing test → implementation → optional refactor.

1. **Task 1: InstallEntry + install_manifest field**
   - `feefb8d` (test): failing tests for model + migration
   - `bdc9b52` (feat): InstallEntry, install_manifest field, version bump, chained migration, _backfill_manifest

2. **Task 2: Init pipeline manifest population**
   - `d61ca8f` (test): failing tests for context + memory.db + tool artifact registration
   - `a253138` (feat): _register helper in context.py, _register_memory_artifact + _register_tool_artifact in orchestrator.py

3. **Task 3: Manifest-driven fresh**
   - `c3ee719` (test): failing tests for orphan reporting, --force, drift warning, empty dir, missing files, cancel
   - `b15218f` (feat): _scan_orphans, _verify_checksum, rewritten fresh with --force flag, empty-dir guard, legacy CLI tests updated

## Files Created/Modified

**Source (4):**
- `flowstate/state.py` — Added `InstallEntry`, `install_manifest` field, bumped version to 0.3.0, refactored `_migrate_state` for chained migration, added `_backfill_manifest`, hooked backfill into `load_state`.
- `flowstate/context.py` — Added `_sha256_of` + `_register` helpers; wired 5 `_register(...)` calls into `write_context_files`.
- `flowstate/orchestrator.py` — Added `_register_memory_artifact` + `_register_tool_artifact`; wired memory.db registration after `MemoryStore(...)` and tool-artifact registration after `update_tool(... artifact=...)` in `_run_step`.
- `flowstate/cli.py` — Deleted `_FRESH_TARGETS` (24 lines); added `_scan_orphans` + `_verify_checksum`; rewrote `fresh` (90+ lines) with `--force` flag, manifest consultation, drift warning, empty-dir guard, empty-subdir sweep.

**Tests (4):**
- `tests/test_install_manifest.py` (new) — 17 tests across 4 test classes covering schema validation, roundtrip, migration, backfill, pipeline registration, fresh command (manifest, force, missing files, drift, cancel, empty dir).
- `tests/test_state.py` — Updated `test_migrate_v010_state` to expect chained migration to v0.3.0; added `test_chained_migration_v010_to_v030`; renamed `test_migrate_v020_noop` to `test_migrate_v030_noop`; updated `test_load_v010_state_file` version assertion.
- `tests/test_context.py` — Added `TestWriteContextFilesManifest` class (3 tests: populates, idempotent, kind mapping).
- `tests/test_orchestrator.py` — Added `test_run_pipeline_registers_tool_artifacts` (verifies research + strategy adapters get manifest entries).
- `tests/test_cli.py` — Rewrote 4 legacy fresh tests to use manifest-driven setup helper `_populate_state_with_manifest`; dropped legacy CONTEXT.md assertion (deliberately out of scope for new orphan scan).

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `Literal[...]` for `InstallEntry.kind` | Pydantic raises `ValidationError` on typos at construction — caught at write time, not at next `fresh` |
| `checksum=None` means "mutable, skip verification" | Cleaner than a separate `mutable: bool` flag; `_verify_checksum(p, None)` returns True |
| Backfill scans **only** known FlowState directories | Avoid surprise inclusion of user-created files in `.planning/`; only the canonical filenames are backfilled |
| Orphan scan bounded to `.planning/`, `research/`, `memory.db`, `flowstate.json` | `.claude/` and source code are explicitly never candidates — safe-by-default |
| Empty-subdir sweep after deletion | Old `_FRESH_TARGETS` removed dirs wholesale; users expect equivalent cleanup |
| Dropped CONTEXT.md from orphan scan | It's v1 cruft, never written by current pipeline; if it exists, user owns it |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Critical functionality] Sweep empty `.planning/research/` subdirectory after orphan removal**
- **Found during:** Task 3 (rewrite fresh)
- **Issue:** Legacy `_FRESH_TARGETS` blind-deleted `.planning/research` as a directory; new manifest-driven fresh only deletes files. After removing `STACK.md`, the empty `.planning/research/` directory lingered. `test_fresh_removes_state_files` failed asserting `not (planning / "research").exists()`.
- **Fix:** Added a leaves-up `rglob` sweep over `.planning/` and `research/` after deletion — any empty subdirectory is `rmdir`'d, including the top-level dirs themselves if empty.
- **Files modified:** `flowstate/cli.py`
- **Verification:** `pytest tests/test_cli.py::test_fresh_removes_state_files` passes.
- **Committed in:** `b15218f`

**2. [Rule 1 — Test alignment] Update legacy state migration tests to expect chained v0.3.0 target**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** `test_migrate_v010_state` asserted `migrated["version"] == "0.2.0"`, but the chained migration now goes all the way to v0.3.0 in one call. Similarly `test_load_v010_state_file` asserted `loaded.version == "0.2.0"`.
- **Fix:** Updated assertions to `"0.3.0"`. Added explicit `test_chained_migration_v010_to_v030` for the full path. Renamed `test_migrate_v020_noop` → `test_migrate_v030_noop` (the v0.2.0 case is no longer a noop).
- **Files modified:** `tests/test_state.py`
- **Verification:** `pytest tests/test_state.py` — all 13 tests pass.
- **Committed in:** `bdc9b52` (bundled with Task 1 GREEN)

**3. [Rule 1 — Test alignment] Rewrite legacy CLI fresh tests to populate manifest**
- **Found during:** Task 3 (GREEN phase)
- **Issue:** Existing tests (`test_fresh_removes_state_files`, `test_fresh_preserves_claude_md`, `test_fresh_cancelled_without_yes`, `test_fresh_removes_empty_planning_dir`) wrote raw files with `{}` content for `flowstate.json` — that's not a valid FlowStateModel JSON, so `load_state` errored. They also assumed blind-delete semantics.
- **Fix:** Added `_populate_state_with_manifest` helper. Each test now uses it to seed the manifest with the files it wants removed. Where appropriate, added `--force` to delete orphans not in the manifest.
- **Files modified:** `tests/test_cli.py`
- **Verification:** `pytest tests/test_cli.py` — all 27 tests pass.
- **Committed in:** `b15218f` (bundled with Task 3 GREEN)

## Verification

- **Test count:** 223 passing (was 196 pre-plan) — +27 new tests for INST coverage.
- **Coverage:** 90.76% overall, `flowstate/state.py` at 93%, `flowstate/cli.py` at 92%, `flowstate/orchestrator.py` at 92%, `flowstate/context.py` at 100%.
- **Manual smoke:** `flowstate fresh --yes` on a brand-new empty directory exits 0 with "Nothing to clean" (no FileNotFoundError).
- **Acceptance criteria:** All 7 success criteria in PLAN.md pass:
  1. `flowstate.json` now contains `install_manifest` array
  2. `flowstate fresh --yes` removes only manifest files; orphans preserved
  3. `flowstate fresh --yes --force` also removes orphans
  4. `flowstate fresh --yes` on empty dir exits 0
  5. Pre-manifest v0.2.0 state triggers disk backfill
  6. Coverage stays ≥80%
  7. All 223 tests green

## Self-Check: PASSED

- File `flowstate/state.py` exists and contains `class InstallEntry(BaseModel)` (line 46), `install_manifest: list[InstallEntry]` (line 81), `version: str = "0.3.0"` (line 66), `def _backfill_manifest` (line 131).
- File `flowstate/context.py` exists and contains 5 `_register(state, root` calls (lines 183, 189, 195, 203, 211) and `import hashlib` (line 9).
- File `flowstate/orchestrator.py` exists and contains `_register_memory_artifact` (line 53), `_register_tool_artifact` (line 71), and 2 `install_manifest.*append` calls (lines 60, 91).
- File `flowstate/cli.py` exists; no `_FRESH_TARGETS` matches; `_scan_orphans` defined (line 347); `state.install_manifest` used in fresh (line 399); `state_path.exists()` guard present (line 397); no `missing_ok` references.
- File `tests/test_install_manifest.py` exists with 17 tests across 4 test classes.
- All 6 task commits exist in git log: `feefb8d`, `bdc9b52`, `d61ca8f`, `a253138`, `c3ee719`, `b15218f`.
- Full test suite: 223 passed, 90.76% coverage.
