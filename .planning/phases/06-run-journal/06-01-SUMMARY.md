---
phase: "06-run-journal"
plan: "01"
status: complete
subsystem: journal
tags: [memory, journal, run-tracking, compounding-loop]
dependency_graph:
  requires: []
  provides: [MemoryKind.RUN, append_run_entry, RUNLOG.md]
  affects: [flowstate/orchestrator.py, flowstate/memory.py]
tech_stack:
  added: []
  patterns: [idempotent-write, delta-snapshot, try-except-non-fatal, timestamp-seam]
key_files:
  created:
    - flowstate/journal.py
    - tests/test_journal.py
  modified:
    - flowstate/memory.py
    - flowstate/orchestrator.py
    - tests/test_memory.py
    - tests/test_orchestrator.py
decisions:
  - "MemoryEntry constructed directly (not via .create()) to pass the timestamp seam into created_at"
  - "append_run_entry imported at module level in orchestrator.py (not lazy) since journal.py has no orchestrator import"
  - "RUNLOG path hard-coded as root/.planning/RUNLOG.md with no caller-supplied override (T-06-01 mitigated)"
  - "Idempotency limit=50 covers up to 50 concurrent runs per session without unbounded query"
metrics:
  duration: "4m 26s"
  completed: "2026-06-08"
  tasks_completed: 3
  files_changed: 6
---

# Phase 06 Plan 01: Run Journal Substrate Summary

**One-liner:** Pure-Python delta journal with SQLite `MemoryKind.RUN` entries and append-only RUNLOG.md mirror wired into `run_pipeline()` before `memory.close()`.

## What Was Built

### Task 1 — MemoryKind.RUN (commit 51a2b63)
Added `RUN = "run"` as the last member of the `MemoryKind` StrEnum in `flowstate/memory.py`. Extended `tests/test_memory.py` with `TestMemoryKindRUN` (3 tests): kind value assertion, fresh-store count=0, add+get_by_kind round-trip.

### Task 2 — flowstate/journal.py (commit db6114f)
Created `flowstate/journal.py` with `append_run_entry(memory, state, run_id, *, root, dry_run, timestamp)`:
- Idempotency guard fetches up to 50 existing RUN entries; returns immediately if run_id already present
- Builds current `{path: checksum}` snapshot from `state.install_manifest`, excluding `memory.db` (checksum=None)
- Diffs against prior RUN entry's stored snapshot to produce `artifacts_changed` list and one-line `delta_line`
- First run (no prior entry): `delta_line = "first run"`, full snapshot stored
- `metadata` dict carries: `run_id`, `snapshot`, `steps`, `artifacts_changed`, `decisions=[]`, `gotchas=[]`, `delta_line`, `dry_run`
- `MemoryEntry` constructed directly (not via `.create()`) to thread the `timestamp` seam into `created_at`
- Dry-run entries get tag `"dry_run"` and `metadata["dry_run"] = True`
- Mirrors to `.planning/RUNLOG.md` via `Path.open("a")` inside `try/except` — write failure is swallowed
- No `flowstate.bridge` import anywhere

15 tests in `tests/test_journal.py` cover all behaviors: first-run snapshot, second-run delta, idempotency, dry_run tagging, RUNLOG content, append ordering (newest-at-bottom), and no-raise on write failure.

### Task 3 — Orchestrator wiring (commit 32138cc)
Added module-level `from flowstate.journal import append_run_entry` to `orchestrator.py`. Inserted call between `save_state(state, root)` and `memory.close()` wrapped in `try/except Exception` matching the existing context-generation failure idiom. Two new tests: one patches `append_run_entry` and asserts `call_count==1` with a 12-char hex `run_id`; the other uses a real `MemoryStore` and asserts `count(MemoryKind.RUN) == 1` after a dry-run pipeline.

## Verification Results

- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` — 401 passed, **92.83% coverage**
- `ruff check flowstate/journal.py flowstate/memory.py flowstate/orchestrator.py` — clean
- `ruff format --check flowstate/journal.py` — already formatted
- `grep 'import.*bridge\|from.*bridge' flowstate/journal.py` — empty (no bridge import)
- `python -m pytest tests/test_state.py -q` — 12 passed (migration chain intact)
- `grep -c 'RUN = "run"' flowstate/memory.py` — 1
- `grep -c 'append_run_entry' flowstate/orchestrator.py` — 2 (import + call)
- append_run_entry (line 315) appears before memory.close() (line 319) in orchestrator.py

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundary changes introduced. RUNLOG.md path is hard-coded as `root / ".planning" / "RUNLOG.md"` per T-06-01 mitigation. No new runtime dependencies added.

## Self-Check: PASSED

- flowstate/journal.py exists and contains `def append_run_entry`
- flowstate/memory.py contains `RUN = "run"`
- flowstate/orchestrator.py contains `append_run_entry` at line 315 (before memory.close() at 319)
- tests/test_journal.py exists (15 tests)
- tests/test_orchestrator.py exists with 2 new journal tests
- Commits 51a2b63, db6114f, 32138cc all present in git log
