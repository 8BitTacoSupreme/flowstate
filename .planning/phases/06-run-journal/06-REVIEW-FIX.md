---
phase: 06-run-journal
fixed_at: 2026-06-07T00:00:00Z
review_path: .planning/phases/06-run-journal/06-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 06: Code Review Fix Report — Run Journal

**Fixed at:** 2026-06-07
**Source review:** .planning/phases/06-run-journal/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8
- Fixed: 8
- Skipped: 0

## Fixed Issues

### CR-01: since-last-run layer excluded from budget accounting

**Files modified:** `flowstate/context_prefix.py`, `tests/test_context_prefix.py`
**Commits:** f46ca51 (fix), 83d8af7 (tests)
**Applied fix:** Moved `since_last_run_layer = _read_since_last_run_layer(...)` to before the pack
fit-ladder so its token cost is included in both `candidate` and `candidate2` strings. Added a
final guard after pack resolution: if the full assembled prefix (fixtures + pack + memory +
since-last-run) >= budget, the since-last-run layer is dropped and logged via `con.print` in
red style (matching the pack-omit log pattern). Test added:
`test_since_last_run_dropped_and_logged_when_over_budget` asserts the layer is dropped or the
prefix stays within budget for oversized RUN entries at a tight budget.

---

### CR-02: idempotency guard misses runs beyond limit=50

**Files modified:** `flowstate/memory.py`, `flowstate/journal.py`
**Commit:** 1ea25d5
**Applied fix:** Extended `MemoryStore.count()` with an optional `run_id: str | None = None`
keyword that adds `AND run_id = ?` to the SQL query (uses the existing `idx_memories_run_id`
index). Replaced the `get_by_kind(limit=50)` + `any(e.run_id == run_id ...)` scan in
`append_run_entry` with `memory.count(MemoryKind.RUN, run_id=run_id) > 0`. The prior-entry
fetch for delta computation is kept as a separate `get_by_kind(limit=1)` call.

---

### WR-01: append_run_entry "never raises" contract not self-contained

**Files modified:** `flowstate/journal.py`, `tests/test_journal.py`
**Commits:** 1ea25d5 (fix in journal.py), c92dda0 (test)
**Applied fix:** Wrapped the `memory.add(entry)` call (step 8) in `try/except Exception: return`
so any SQLite error or other exception from the write path is swallowed inside
`append_run_entry` itself rather than relying on the orchestrator wrapper. Step 9 (RUNLOG
mirror) is only reached when `memory.add` succeeds. Test added:
`TestNeverRaises.test_memory_add_failure_does_not_propagate` uses a MagicMock store whose
`add()` raises `RuntimeError`; asserts the function returns without propagating.

---

### WR-02: memory search --kind Choice missing "run"

**Files modified:** `flowstate/cli.py`
**Commit:** 9f008d1
**Applied fix:** Added `"run"` to the `click.Choice([...])` list for the `--kind` option on
`memory search`. `flowstate memory search --kind run <query>` now works correctly.

---

### WR-03: bool silently accepted as int config

**Files modified:** `flowstate/context_prefix.py`, `tests/test_context_prefix.py`
**Commits:** f46ca51 (fix), 83d8af7 (tests)
**Applied fix:** Changed both `_load_budget` (L81) and `_load_journal_prefix_n` (L100) guards
from `isinstance(value, int) and value > 0` to
`isinstance(value, int) and not isinstance(value, bool) and value > 0`. JSON `true`/`false`
now fall back to the default instead of passing as `1`/`0`. Two tests added:
`test_bool_config_falls_back_to_default_journal_prefix_n` and
`test_bool_config_falls_back_to_default_budget`.

---

### IN-01: unused `state` parameter removed from `_build_delta_line`

**Files modified:** `flowstate/journal.py`
**Commit:** 1ea25d5
**Applied fix:** Removed the `state: FlowStateModel` parameter from `_build_delta_line` and
updated its single call site at line 60 to `_build_delta_line(artifacts_changed)`.

---

### IN-02: unreachable `else ""` redundancy removed

**Files modified:** `flowstate/journal.py`
**Commit:** 1ea25d5
**Applied fix:** Changed `sample = artifacts_changed[0] if artifacts_changed else ""` to
`sample = artifacts_changed[0]` with a clarifying comment. The empty-list guard at line 118
makes the ternary unreachable.

---

### IN-03: missing test for removed-path delta branch

**Files modified:** `tests/test_journal.py`
**Commit:** c92dda0
**Applied fix:** Added `TestRemovedPathDelta.test_removed_path_appears_in_artifacts_changed`
which seeds run001 with two manifest entries, removes `.planning/ROADMAP.md` from the manifest
before run002, and asserts the removed path appears in `artifacts_changed`. Covers the
previously uncovered branch at `journal.py:59`.

---

## Verification Results

All checks run from `/Users/jhogan/frameworx` after applying all fixes:

```
pytest: 415 passed, 0 failed — coverage 92.85% (>=80% required)
ruff check: All checks passed
ruff format --check: 54 files already formatted
grep -c 'import.*bridge' journal.py context_prefix.py: 0 0
```

---

_Fixed: 2026-06-07_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
