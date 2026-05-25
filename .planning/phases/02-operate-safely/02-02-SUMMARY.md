---
phase: 02-operate-safely
plan: 02
subsystem: cli-health
tags: [doctor, repair, pydantic-v2, model_copy, sqlite, fts5, sha256, click, rich]

# Dependency graph
requires:
  - phase: 02-operate-safely
    provides: install_manifest field on FlowStateModel + InstallEntry model (Plan 01)
provides:
  - Diagnosis frozen dataclass (name/severity/message/fix_hint)
  - 6 pure-Python health checks (manifest_integrity, memory_schema, root_resolution, claude_cli, stale_status, orphan_files)
  - run_doctor aggregator that never raises (per-check exception → error Diagnosis)
  - apply_safe_fixes (regenerate context files, recreate memory schema, reset stale Running, update drifted checksums via model_copy)
  - apply_destructive_fixes (delete orphans, recreate unreadable memory.db)
  - flowstate doctor + flowstate repair Click commands with --apply-destructive gate
  - healthy_install pytest fixture using monkeypatch.setenv (W4 CliRunner env-isolation pattern)
affects: [02-03-status (consumes nothing yet), future phases that need health monitoring]

tech-stack:
  added: []  # No new runtime deps — stdlib hashlib, sqlite3, dataclasses, typing.Literal
  patterns:
    - "Pure-Python diagnose-then-fix split: doctor returns Diagnosis records, repair consumes them by name"
    - "Late-binding module-level checks in run_doctor (import flowstate.doctor as _self) so monkeypatch in tests reaches the dispatched call"
    - "Pydantic v2 immutability-safe field updates via entry.model_copy(update={...}) + rebuilt list — never attribute assignment"
    - "Safe-by-default destructive gating: caller must explicitly invoke apply_destructive_fixes with diagnoses; CLI gates on --apply-destructive flag"
    - "Exit code = error count: doctor composes in CI / pre-commit hooks via sys.exit(errors)"
    - "CliRunner env propagation via monkeypatch.setenv (writes to os.environ) instead of env= per-call plumbing"

key-files:
  created:
    - flowstate/doctor.py
    - flowstate/repair.py
    - tests/test_doctor.py
    - tests/test_repair.py
  modified:
    - flowstate/cli.py
    - tests/test_cli.py

key-decisions:
  - "Doctor checks return list[Diagnosis] not single Diagnosis — manifest_integrity can yield multiple findings (one per drifted/missing file)"
  - "checksum=None entries (memory.db) skip checksum verification; only file-existence is checked"
  - "Memory schema check requires memories + memories_fts + schema_version tables — strictly catches partial init"
  - "run_doctor uses late-binding (import flowstate.doctor as _self) so test monkeypatches of module-level checks take effect"
  - "model_copy(update=...) chosen over enabling Pydantic mutability — keeps InstallEntry immutable everywhere else (B3 Option A from plan-checker iteration 1)"
  - "Safe fix for memory_schema EXCLUDES unreadable-db case — that's destructive (deletes file before recreating)"
  - "healthy_install fixture uses monkeypatch.setenv per W4 — CliRunner.invoke inherits os.environ but not pytest monkeypatch scope unless setenv writes to os.environ"

patterns-established:
  - "Diagnosis-driven repair: future health checks should add a check_* fn in doctor.py and a matching diagnosis-name branch in repair.py — no new CLI surface"
  - "Pydantic-immutable-safe mutation: any future field update on InstallEntry (or similar BaseModel) must use model_copy(update=...) + rebuilt list, never in-place assignment"
  - "Pure-Python diagnose modules: no LLM dependency, composable in pre-commit/CI, dataclass results for structured introspection"

requirements-completed: [DOCT-01, DOCT-02]

# Metrics
duration: ~6min
completed: 2026-05-25
---

# Phase 2 Plan 2: Doctor + Repair Summary

**`flowstate doctor` runs 6 pure-Python health checks (manifest integrity, memory schema, root, claude CLI, stale Running statuses, orphans) with exit-code = error count; `flowstate repair` applies the safe subset by default and gates orphan-deletion + corrupt-db recreation behind `--apply-destructive`, using Pydantic-immutable-safe `model_copy(update={...})` for checksum drift updates.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-25T19:20:40Z
- **Completed:** 2026-05-25T19:26Z
- **Tasks:** 3 / 3
- **Files modified:** 6 (4 new, 2 modified)
- **Test count:** 289 passing (up from 247 before this plan — +42 new tests for DOCT)
- **Coverage:** 91.45% (above 80% floor)

## Accomplishments

- **DOCT-01 — Doctor module landed:** New `flowstate/doctor.py` with frozen `Diagnosis` dataclass, 6 independent check functions, and `run_doctor()` aggregator that never raises (per-check exceptions become `<name>_failed` error diagnoses). `STALE_RUNNING_HOURS = 24` constant. Pure-Python — composes in CI/pre-commit via exit-code = error count.
- **DOCT-02 — Repair module landed:** New `flowstate/repair.py` with `apply_safe_fixes()` and `apply_destructive_fixes()`. Safe path regenerates missing context files (via `write_context_files`), recreates `memory.db` schema (idempotent `CREATE IF NOT EXISTS`), resets stale Running statuses to BLOCKED, and updates drifted checksums via `entry.model_copy(update={"checksum": actual})` + rebuilt manifest list. Destructive path deletes orphan files in `.planning/`/`research/` and recreates unreadable `memory.db`.
- **CLI integration:** `flowstate doctor` prints a Rich table (Check/Severity/Message) and exits with `errors` count; healthy install prints "All checks passed" and exits 0. `flowstate repair` runs doctor, applies safe fixes, saves state, and skips destructive fixes unless `--apply-destructive` passed.
- **CliRunner env-isolation pattern landed:** `healthy_install` fixture uses `monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", ...)` per plan-checker W4 — CliRunner.invoke inherits os.environ (which setenv writes to), so no `env=` plumbing per-call needed.

## Task Commits

Each task followed strict TDD (failing test → implementation):

1. **Task 1: doctor.py + tests**
   - `9d58bf1` (test): failing tests for 6 checks + Diagnosis + run_doctor
   - `d25818a` (feat): create flowstate/doctor.py — Diagnosis dataclass, 6 checks, run_doctor with late-binding

2. **Task 2: repair.py + tests**
   - `4f5cbb5` (test): failing tests for apply_safe_fixes + apply_destructive_fixes + KNOWN_CONTEXT_FILES
   - `71fd8e0` (feat): create flowstate/repair.py — safe vs destructive split, model_copy checksum updates

3. **Task 3: CLI integration + tests**
   - `6706220` (test): failing tests for TestDoctorCommand + TestRepairCommand + healthy_install fixture
   - `4c645d3` (feat): wire @main.command("doctor") + @main.command("repair") with Rich-table output and exit-code semantics

## Files Created/Modified

**Source (3 — 2 new, 1 modified):**
- `flowstate/doctor.py` (new, 224 lines) — `Diagnosis` frozen dataclass, `check_manifest_integrity`, `check_memory_schema`, `check_root_resolution`, `check_claude_cli`, `check_stale_status`, `check_orphan_files`, `run_doctor` aggregator with per-check exception handling. Late-binds module-level checks inside `run_doctor` so test monkeypatches reach the dispatched call.
- `flowstate/repair.py` (new, 145 lines) — `KNOWN_CONTEXT_FILES` set, `apply_safe_fixes` (4 fix categories), `apply_destructive_fixes` (2 fix categories). Uses `entry.model_copy(update={"checksum": actual})` + rebuilt manifest list (NOT in-place mutation, which raises ValidationError on Pydantic v2 validate-on-assignment models).
- `flowstate/cli.py` (+109 lines) — Added `@main.command("doctor")` (Rich-table output, sys.exit(errors)) and `@main.command("repair")` (--apply-destructive flag, save_state after fixes).

**Tests (3 — 2 new, 1 modified):**
- `tests/test_doctor.py` (new, 244 lines) — 23 tests across 7 classes covering Diagnosis frozenness, each check's happy + failure modes, run_doctor aggregation + exception handling, STALE_RUNNING_HOURS constant.
- `tests/test_repair.py` (new, 161 lines) — 10 tests across 3 classes covering safe-fix application (each category), destructive-fix application (each category), gating semantics, KNOWN_CONTEXT_FILES contents.
- `tests/test_cli.py` (+145 lines) — Added `healthy_install` fixture (monkeypatch.setenv pattern) + `TestDoctorCommand` (4 tests) + `TestRepairCommand` (5 tests).

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Checks return `list[Diagnosis]` not single | `manifest_integrity` can find multiple drifted/missing files; uniform return type simplifies aggregation |
| Late-binding `import flowstate.doctor as _self` in `run_doctor` | Tests monkeypatch `flowstate.doctor.check_manifest_integrity`; if `run_doctor` captured the symbol at module load time, the patch wouldn't reach the dispatched call |
| `model_copy(update={...})` over enabling Pydantic mutability | Keeps InstallEntry immutable everywhere else; only the repair code path needs to update checksums, and the canonical Pydantic v2 idiom is model_copy (B3 Option A from plan-checker iteration 1) |
| Safe fix for memory_schema EXCLUDES unreadable case | Recreating a corrupt DB requires deletion first — that's destructive; safe path only re-applies idempotent `CREATE IF NOT EXISTS` |
| `monkeypatch.setenv` in healthy_install fixture (vs `env=` per invoke) | `monkeypatch.setenv` writes to `os.environ`, which `CliRunner.invoke` inherits; alternative would require threading `env={...}` through every test call (W4 pattern) |
| `STALE_RUNNING_HOURS = 24` constant | 24h matches typical overnight gap; explicit constant lets future deployments tune via subclass without forking |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `run_doctor` late-binding for monkeypatch reach**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Plan's `run_doctor` skeleton called `check_manifest_integrity(state, root)` etc. directly. Tests monkeypatch `flowstate.doctor.check_manifest_integrity` to raise, expecting `run_doctor` to convert that into a `<name>_failed` diagnosis. Direct calls bind the symbol at function-definition time, so monkeypatch on the module attribute doesn't reach the call inside `run_doctor`.
- **Fix:** Added `import flowstate.doctor as _self` inside `run_doctor` and dispatched through `_self.check_manifest_integrity(...)` etc. This is the canonical Python idiom for "make module-level functions monkeypatchable from within the same module."
- **Files modified:** `flowstate/doctor.py`
- **Verification:** `TestRunDoctor::test_check_exception_becomes_error_diagnosis` passes — confirms `manifest_integrity_failed` appears in findings when the check is monkeypatched to raise.
- **Committed in:** `d25818a` (bundled with Task 1 GREEN)

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Single small correctness fix to make the run_doctor aggregator monkeypatchable as the tests required. No scope creep.

## Issues Encountered

- None. Plan executed cleanly. The model_copy pattern from plan-checker iteration 1 worked exactly as specified — no ValidationError encountered.

## Verification

- **Plan-scope tests:** `pytest tests/test_doctor.py tests/test_repair.py tests/test_cli.py::TestDoctorCommand tests/test_cli.py::TestRepairCommand` → 42 passed.
- **Full suite:** `pytest tests/` → **289 passed, 0 failed**, coverage **91.45%** (well above 80% floor).
- **Manual smoke:** `python -m flowstate doctor --help` and `python -m flowstate repair --help` both exit 0 with the expected option lists.
- **Acceptance criteria — all met:**
  - `grep '@dataclass(frozen=True)' flowstate/doctor.py` → match (Diagnosis)
  - 7 named functions present in doctor.py (`check_manifest_integrity`, `check_memory_schema`, `check_root_resolution`, `check_claude_cli`, `check_stale_status`, `check_orphan_files`, `run_doctor`)
  - `STALE_RUNNING_HOURS = 24` present
  - `model_copy(update=` present in repair.py
  - No `entry.checksum =` real assignment (only comment reference)
  - `monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN"` present in tests/test_cli.py healthy_install fixture
  - 2 `@main.command("doctor")` / `@main.command("repair")` decorators present in cli.py
  - 23 doctor tests + 10 repair tests + 9 CLI tests = 42 new tests collected

## Next Phase Readiness

- Doctor + repair surface ready. Future phases can compose `run_doctor()` directly (e.g., a pre-commit hook that calls it and exits with the error count).
- `model_copy` pattern documented for any future Pydantic-immutable-safe mutations.
- Plan 02-03 (status --markdown) and Plan 02-04 (hook env-gating) complete; phase 02 now has 4/4 plans done.

## Self-Check: PASSED

- File `flowstate/doctor.py` exists (224 lines, contains `class Diagnosis`, 6 `def check_*` functions, `def run_doctor`, `STALE_RUNNING_HOURS = 24`).
- File `flowstate/repair.py` exists (145 lines, contains `def apply_safe_fixes`, `def apply_destructive_fixes`, `KNOWN_CONTEXT_FILES` set, `model_copy(update=`).
- File `flowstate/cli.py` modified — `@main.command("doctor")` at line 526, `@main.command("repair")` at line 577, `--apply-destructive` flag at line 585.
- File `tests/test_doctor.py` exists (244 lines, 7 test classes, 23 tests, all pass).
- File `tests/test_repair.py` exists (161 lines, 3 test classes, 10 tests, all pass).
- File `tests/test_cli.py` modified — `healthy_install` fixture with `monkeypatch.setenv`, `TestDoctorCommand` (4 tests), `TestRepairCommand` (5 tests).
- All 6 task commits exist in git log: `9d58bf1`, `d25818a`, `4f5cbb5`, `71fd8e0`, `6706220`, `4c645d3`.
- Full test suite: **289 passed, 91.45% coverage**.

---
*Phase: 02-operate-safely*
*Completed: 2026-05-25*
