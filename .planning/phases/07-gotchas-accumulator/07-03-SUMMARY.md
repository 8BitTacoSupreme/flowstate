---
phase: 07-gotchas-accumulator
plan: "03"
subsystem: cli
status: complete
tags: [click, rich, sqlite, gotchas, doctor, repair]

requires:
  - phase: 07-01
    provides: capture_gotcha, _rewrite_gotchas_md, MemoryStore.update — gotchas core module

provides:
  - flowstate gotchas command group (list + prune subcommand)
  - doctor/repair best-effort capture wiring for error/warning diagnoses

affects:
  - Phase 08 (verify) — any new CLI command adding gotcha captures can follow same wiring pattern

tech-stack:
  added: []
  patterns:
    - "@main.group(invoke_without_command=True) for list-or-subcommand pattern"
    - "best-effort try/except capture block in doctor/repair after run_doctor()"
    - "COLUMNS=200 env in CliRunner for Rich table width in tests"

key-files:
  created: []
  modified:
    - flowstate/cli.py
    - tests/test_cli.py

key-decisions:
  - "gotchas group uses invoke_without_command=True so bare 'flowstate gotchas' lists and 'gotchas prune' is a subcommand"
  - "Signature column uses min_width=16 (not width=) so 16-char hex signatures are not truncated by Rich"
  - "Tests use COLUMNS=200 env to force wide Rich terminal in CliRunner — avoids Rich table truncation"
  - "Doctor/repair capture block placed BEFORE display/exit logic so it runs regardless of error count"
  - "Patch targets flowstate.state.load_state and flowstate.doctor.run_doctor (not flowstate.cli.*) since these are locally imported"

requirements-completed: [GOT-01, GOT-03]

duration: 35min
completed: 2026-06-08
---

# Phase 07 Plan 03: Gotchas CLI Command + Doctor/Repair Capture Summary

**`flowstate gotchas` list/prune command with count-desc Rich table, graceful empty/corrupt degrade, and best-effort gotcha capture wired into doctor and repair for error/warning severity findings**

## Performance

- **Duration:** 35 min
- **Started:** 2026-06-08T23:00:00Z
- **Completed:** 2026-06-08T23:35:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `flowstate gotchas` lists INSIGHT+gotcha entries sorted count-desc/recency with Rich table, exits 0 on empty/corrupt DB (no traceback)
- `flowstate gotchas prune --signature <sig>` deletes by metadata.signature via parameterized DELETE; prune --resolved clears "resolved"-tagged entries; both rewrite GOTCHAS.md mirror
- `flowstate doctor` and `flowstate repair` now capture error/warning Diagnosis records as source=doctor gotchas immediately after run_doctor(); wrapped in try/except so corrupt DB never changes exit codes

## Task Commits

1. **RED — failing tests** - `b1522e0` (test)
2. **Task 1+2: gotchas command + doctor/repair capture** - `4dd56a5` (feat)

## Files Created/Modified

- `/Users/jhogan/frameworx/flowstate/cli.py` — `gotchas_group` command group + `gotchas_prune` subcommand + capture blocks in doctor and repair
- `/Users/jhogan/frameworx/tests/test_cli.py` — TestGotchasCommand (5 tests), TestGotchasPruneCommand (3 tests), TestDoctorGotchaCapture (4 tests), TestRepairGotchaCapture (2 tests)

## Decisions Made

- `@main.group("gotchas", invoke_without_command=True)` pattern chosen over a plain `@main.command` + separate group, keeping `prune` discoverable as a subcommand while keeping the bare command useful
- Signature column changed to `min_width=16` (from plan spec `width=12`) to prevent Rich truncating 16-char hex signatures
- CLI tests use `env={"COLUMNS": "200"}` in CliRunner invocations that check Message column content — Rich respects COLUMNS to set console width
- Patch targets are `flowstate.state.load_state` and `flowstate.doctor.run_doctor` (module-level import locations) since these names live in local function imports in cli.py, not at module namespace level
- Capture blocks placed BEFORE the `if not findings: return` check so they execute even when there are only warnings (no errors to sys.exit on)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Signature column width adjusted from plan spec width=12 to min_width=16**
- **Found during:** Task 1 (GREEN implementation)
- **Issue:** Plan spec said "Signature(12)" but 16-char hex signatures were silently truncated by Rich's fixed-width column rendering
- **Fix:** Changed to `min_width=16` so column expands to fit full signature
- **Files modified:** flowstate/cli.py
- **Committed in:** 4dd56a5

**2. [Rule 1 - Bug] Test patch targets corrected from flowstate.cli.* to actual module paths**
- **Found during:** Task 2 (RED + GREEN)
- **Issue:** `patch("flowstate.cli.load_state")` raised AttributeError because load_state is locally imported inside function bodies, not at cli module namespace level
- **Fix:** Changed to `patch("flowstate.state.load_state")` and `patch("flowstate.doctor.run_doctor")` (the canonical module paths)
- **Files modified:** tests/test_cli.py
- **Committed in:** 4dd56a5

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs discovered during implementation)
**Impact on plan:** No scope change. Both fixes required for correct behavior. Column width fix improves UX.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Known Stubs

None — all wiring is live (capture_gotcha, _rewrite_gotchas_md, MemoryStore.update all provided by 07-01).

## Next Phase Readiness

- GOT-01 (doctor/repair source) and GOT-03 (prune + display) are complete
- `flowstate gotchas` is ready for Phase 8 (verify) to add gotcha captures via the same capture_gotcha API
- GOTCHAS.md mirror is kept in sync on every capture and prune

---
*Phase: 07-gotchas-accumulator*
*Completed: 2026-06-08*
