---
phase: 07-gotchas-accumulator
plan: "04"
subsystem: memory
status: complete
tags: [gotchas, memory-handlers, journal, orchestrator, dedup, run_id]

requires:
  - phase: 07-01
    provides: capture_gotcha + harvest_planning_gotchas in flowstate/gotchas.py

provides:
  - on_step_failed extended to capture executor gotchas (source=executor, severity=error) alongside existing TOOL_RUN store
  - harvest_planning_gotchas called once at pipeline start (non-fatal) in run_pipeline
  - journal metadata["gotchas"] slot populated with this run's captured signatures (delta-only)
  - RUNLOG.md gotchas line shows actual signatures or "(none this run)" instead of placeholder

affects: [journal-command, context-prefix, phase-08-verify]

tech-stack:
  added: []
  patterns:
    - "Lazy import inside handler to avoid circular import (gotchas.py -> memory.py chain)"
    - "Best-effort try/except: pass after existing TOOL_RUN store — existing behavior preserved"
    - "run_id threaded through capture_gotcha so journal can match gotchas to this pipeline run"
    - "delta-only signature list in journal metadata (not full content)"
    - "decisions line updated from '(none this phase)' to '(none this run)' for consistency"

key-files:
  modified:
    - flowstate/memory_handlers.py
    - flowstate/orchestrator.py
    - flowstate/journal.py
    - tests/test_memory_handlers.py
    - tests/test_orchestrator.py
    - tests/test_journal.py

key-decisions:
  - "Lazy import of capture_gotcha inside on_step_failed avoids circular import risk (gotchas->memory<-memory_handlers)"
  - "Existing TOOL_RUN store.add call preserved untouched; gotcha capture is additive AFTER it"
  - "Journal queries INSIGHT+gotcha entries filtered by run_id — in-band, no threading needed"
  - "decisions line in RUNLOG also updated to '(none this run)' for consistency with gotchas line"
  - "harvest insertion point: immediately after MemoryStore opens, before interview answer memory write"

patterns-established:
  - "Executor failure hook pattern: TOOL_RUN store first, gotcha capture second (additive, non-fatal)"
  - "Journal gotchas slot: query store for INSIGHT entries with run_id match + gotcha tag, extract signatures"
  - "Best-effort harvest at pipeline start mirrors append_run_entry guard (try/except with console yellow log)"

requirements-completed: [GOT-01]

duration: 20min
completed: "2026-06-08"
---

# Phase 07 Plan 04: Gotchas Pipeline Wiring Summary

**Executor failures captured as deduped gotchas via on_step_failed; harvest_planning_gotchas runs at pipeline start; journal metadata gotchas slot populated with this run's captured signatures**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-08T23:00:00Z
- **Completed:** 2026-06-08T23:14:06Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Extended `on_step_failed` in `memory_handlers.py` to also call `capture_gotcha(source="executor")` after the existing TOOL_RUN store.add — dedup via signature, run_id threaded through
- Added `harvest_planning_gotchas(memory, root)` call in `run_pipeline` immediately after MemoryStore opens, wrapped in try/except, never fatal
- Replaced `metadata["gotchas"] = []` placeholder in `append_run_entry` with an in-band query for INSIGHT+gotcha entries matching this run_id, collecting signatures delta-only
- Updated `_append_runlog` to accept `gotchas: list[str]` and write actual signatures (or `"(none this run)"`) — old `"(none this phase)"` placeholder gone from both gotchas and decisions lines

## Task Commits

1. **Task 1: Extend on_step_failed to also capture an executor gotcha** - `f12b30d` (feat)
2. **Task 2: Harvest planning gotchas at pipeline start + populate journal gotchas slot** - `dd73688` (feat)

## Files Created/Modified

- `flowstate/memory_handlers.py` - Added best-effort `capture_gotcha` call after existing TOOL_RUN store.add in `on_step_failed`; lazy import avoids circular-import risk
- `flowstate/orchestrator.py` - Added `harvest_planning_gotchas` call immediately after `MemoryStore(root=root)` opens, before first adapter step
- `flowstate/journal.py` - Replaced `metadata["gotchas"] = []` with live INSIGHT query filtered by run_id; `_append_runlog` now accepts and writes actual gotcha signatures; placeholder removed
- `tests/test_memory_handlers.py` - 4 new tests: executor gotcha captured, dedup (count=2), run_id set, capture failure non-fatal; updated test_stores_failure to assert TOOL_RUN count specifically
- `tests/test_orchestrator.py` - 2 new tests: harvest called once, harvest failure non-fatal
- `tests/test_journal.py` - 5 new tests in TestGotchasSlot: empty slot, populated slot, run_id scoped, RUNLOG none-this-run, RUNLOG shows signatures

## Decisions Made

- Lazy import of `capture_gotcha` inside `on_step_failed` — `gotchas.py` imports from `memory.py`; `memory_handlers.py` also imports from `memory.py`; keeping the import lazy avoids any circular risk
- Existing TOOL_RUN `store.add(...)` call left untouched — gotcha capture is additive AFTER it, never before; existing behavior preserved (regression test updated to assert TOOL_RUN count, not total count)
- In-band query approach for journal gotchas slot — `append_run_entry` queries the store for INSIGHT entries matching `run_id` rather than threading signatures through — simpler call site
- Harvest insertion point: after `MemoryStore(root=root)` and handler registration, before interview answer seeding — this ensures prior-phase artifacts are in memory before any adapter step
- `decisions` RUNLOG line also updated from `(none this phase)` → `(none this run)` for consistency; acceptance criteria required zero occurrences of the old phrase in journal.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_stores_failure assertion to match new behavior**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Existing test asserted `mem_store.count() == 1` but after adding gotcha capture, a step.failed now produces 2 entries (1 TOOL_RUN + 1 INSIGHT gotcha). The test was written assuming single-entry behavior.
- **Fix:** Changed assertion to `get_by_kind(MemoryKind.TOOL_RUN)` count == 1 (the actual regression being guarded — TOOL_RUN entry count is unchanged)
- **Files modified:** `tests/test_memory_handlers.py`
- **Verification:** All 12 memory handler tests pass
- **Committed in:** f12b30d (Task 1 commit)

**2. [Rule 2 - Missing Critical] Updated decisions RUNLOG line from "none this phase" to "none this run"**
- **Found during:** Task 2 verification (acceptance criteria `grep -c 'none this phase' flowstate/journal.py == 0`)
- **Issue:** Acceptance criteria required zero occurrences of "none this phase" in journal.py. The `decisions` line still used that phrase.
- **Fix:** Changed `"- decisions: (none this phase)\n"` to `"- decisions: (none this run)\n"` for consistency with the gotchas line update
- **Files modified:** `flowstate/journal.py`
- **Verification:** `grep -c 'none this phase' flowstate/journal.py` returns 0
- **Committed in:** dd73688 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 test regression, 1 missing critical acceptance criterion)
**Impact on plan:** Both essential for correctness. No scope creep.

## Issues Encountered

None — both tasks executed cleanly after the test regression fix.

## Self-Check: PASSED

- SUMMARY.md: FOUND at .planning/phases/07-gotchas-accumulator/07-04-SUMMARY.md
- Commit f12b30d: FOUND (Task 1 — on_step_failed executor gotcha)
- Commit dd73688: FOUND (Task 2 — harvest + journal gotchas slot)

## Next Phase Readiness

- GOT-01 complete: executor source wired (Task 1), harvest sources 3-4 wired (Task 2), journal gotchas slot closed (Task 2)
- Phase 08 (verify) can now capture verifier failures as gotchas via `capture_gotcha(source="verifier")` and those will automatically appear in the journal gotchas slot for subsequent runs
- All 503 tests pass, coverage 92.21%

---
*Phase: 07-gotchas-accumulator*
*Completed: 2026-06-08*
