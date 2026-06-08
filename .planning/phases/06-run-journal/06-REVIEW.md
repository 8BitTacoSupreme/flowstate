---
phase: 06-run-journal
reviewed: 2026-06-07T00:00:00Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - flowstate/journal.py
  - flowstate/memory.py
  - flowstate/orchestrator.py
  - flowstate/context_prefix.py
  - flowstate/cli.py
  - tests/test_journal.py
  - tests/test_context_prefix.py
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 06: Code Review Report — Run Journal

**Reviewed:** 2026-06-07
**Depth:** deep
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 6 delivers a pure-Python run-journal subsystem: `journal.py` (new), `MemoryKind.RUN`
addition, orchestrator call-site, a fourth CAG layer (`since-last-run`) in `context_prefix.py`,
and the `journal` CLI command. All 410 tests pass at 92.82% coverage. The "never bridge" and
"never raises into pipeline" contracts are structurally sound. The implementation is clean
overall with two correctness blockers and three warnings worth fixing before the milestone closes.

---

## Critical Issues

### CR-01: `since-last-run` layer excluded from budget accounting — final prefix silently exceeds budget

**File:** `flowstate/context_prefix.py:220,234-235`

**Issue:** The pack-fit-ladder candidate strings at lines 220 and 234-235 include only
`[fixtures_layer, pack_raw/pack_compressed, memory_layer]`. The `since_last_run_layer` is
assembled at line 258 and appended unconditionally at line 261 — it is never counted against
the budget. If the store holds several verbose RUN entries (e.g., 3 × large delta content),
the final prefix can silently exceed `budget_tokens` by an unbounded amount, defeating the
cache-window guarantee the budget is designed to enforce.

This is a correctness bug, not a style issue: the docstring and the constant name
`context_prefix_budget_tokens` both imply a hard ceiling on the returned string size.

**Fix:** Include the `since_last_run_layer` in both candidate strings, or cap the
`since_last_run_layer` separately and account for it:

```python
# After building since_last_run_layer, check the full assembly against budget
# and trim (or drop) the layer if needed.
since_last_run_layer = _read_since_last_run_layer(root, memory)

# Build full candidate to check total
full_candidate = _SEPARATOR.join(
    filter(None, [fixtures_layer, pack_layer, memory_layer, since_last_run_layer])
)
if _estimate_tokens(full_candidate) > budget:
    # Drop since_last_run rather than silently overshoot
    since_last_run_layer = ""
```

Or, simpler: pre-estimate the `since_last_run_layer` cost before the pack fit-ladder and
reduce the remaining budget available to the pack accordingly.

---

### CR-02: Idempotency guard can miss runs when more than 50 RUN entries exist

**File:** `flowstate/journal.py:36-37`

**Issue:** The idempotency check fetches only the 50 most-recent RUN entries
(`get_by_kind(MemoryKind.RUN, limit=50)`) and scans them with `any(e.run_id == run_id ...)`.
If a project has more than 50 prior pipeline runs and the same `run_id` is replayed
(e.g., state file restored from backup), entries 51+ are never checked. A duplicate
MemoryKind.RUN record is silently written.

The index `idx_memories_run_id` already exists; a direct SQL COUNT is both cheaper and
correct at any scale.

**Fix:** Replace the linear scan with a targeted query:

```python
# journal.py – replace the existing guard block
row = memory._conn.execute(
    "SELECT COUNT(*) as cnt FROM memories WHERE kind = ? AND run_id = ?",
    (MemoryKind.RUN.value, run_id),
).fetchone()
if row["cnt"] > 0:
    return
```

If direct `_conn` access is undesirable, add a `MemoryStore.exists_run_id(run_id)` helper
or a `get_by_kind_and_run_id` method that queries by both columns.

---

## Warnings

### WR-01: `append_run_entry` "never raises" contract is partially delegated to the orchestrator

**File:** `flowstate/journal.py:97-110` and `flowstate/orchestrator.py:314-317`

**Issue:** The module docstring and function docstring both state "Never raises — journal
failures must not break the pipeline." However, `memory.add(entry)` at line 110 is called
**outside** any `try/except` inside `append_run_entry`. If `memory.add` raises (SQLite
`OperationalError`, `IntegrityError` on an id collision, disk-full mid-write, etc.), the
exception propagates out of `append_run_entry`. The pipeline is saved only by the orchestrator
wrapper at `orchestrator.py:314-317` — a caller-level safety net rather than a local one.

The documented contract (`append_run_entry` never raises) does not hold when called outside
the orchestrator (e.g., directly from a test or a future CLI command). `TestNeverRaises` in
`test_journal.py` only exercises RUNLOG write failure, not `memory.add` failure.

**Fix:** Wrap the `memory.add(entry)` call:

```python
# journal.py – step 8
try:
    memory.add(entry)
except Exception:
    return  # memory write failed; RUNLOG is best-effort too, skip it

# step 9 — only reached when memory.add succeeded
_append_runlog(root, run_id, ts, steps, artifacts_changed, delta_line, dry_run)
```

Add a test that monkeypatches `memory.add` to raise and verifies `append_run_entry` returns
without propagating.

---

### WR-02: `memory search --kind` choice list missing `"run"`

**File:** `flowstate/cli.py:333`

**Issue:** `MemoryKind.RUN` was added to `memory.py`, and `journal.py` writes entries with
`kind="run"`. The `memory search --kind` option's `click.Choice` list at line 333 still
enumerates only the original five kinds and omits `"run"`:

```python
type=click.Choice(["research", "strategy", "decision", "tool_run", "insight"]),
```

`flowstate memory search --kind run <query>` will fail with a Click `BadParameter` error.
Users who want to search RUN entries by kind via the CLI cannot do so.

**Fix:**
```python
type=click.Choice(["research", "strategy", "decision", "tool_run", "insight", "run"]),
```

---

### WR-03: `bool` values in config.json silently accepted as valid budget/limit integers

**File:** `flowstate/context_prefix.py:81,100`

**Issue:** Both `_load_budget` and `_load_journal_prefix_n` validate with
`isinstance(value, int) and value > 0`. In Python, `bool` is a subclass of `int`, so
`{"context_prefix_budget_tokens": true}` passes validation and sets the token budget to `1`.
This means every pack will be considered "over budget" and dropped, with no error message
distinguishing it from a genuine tight budget. The RUNLOG.md and context-prefix output will
silently degrade without any diagnostic.

**Fix:** Add a `not isinstance(value, bool)` guard:

```python
if isinstance(value, int) and not isinstance(value, bool) and value > 0:
    return value
```

---

## Info

### IN-01: `_build_delta_line` accepts an unused `state` parameter

**File:** `flowstate/journal.py:116`

**Issue:** The private function signature is
`def _build_delta_line(artifacts_changed: list[str], state: FlowStateModel) -> str:`.
The `state` argument is never used inside the function body. This is dead weight that
misleads readers into thinking `state` is consulted for the delta message.

**Fix:** Remove the parameter and update the call site:

```python
# journal.py line 116
def _build_delta_line(artifacts_changed: list[str]) -> str:

# journal.py line 60
delta_line = _build_delta_line(artifacts_changed)
```

---

### IN-02: Redundant guard in `_build_delta_line` (dead code at line 121)

**File:** `flowstate/journal.py:121`

**Issue:** Line 121 reads `sample = artifacts_changed[0] if artifacts_changed else ""`. The
`if artifacts_changed else ""` branch is unreachable: lines 118-119 already return
`"no changes detected"` when the list is empty. The list is guaranteed non-empty by this
point, making the ternary dead code.

**Fix:**
```python
sample = artifacts_changed[0]  # guaranteed non-empty — line 118 guards the empty case
```

---

### IN-03: Missing test coverage for "removed path" delta branch

**File:** `tests/test_journal.py` (coverage for `flowstate/journal.py:59`)

**Issue:** Coverage report shows `journal.py:59` uncovered. This is the branch:
```python
for path in prior_snapshot:
    if path not in current_snapshot:
        artifacts_changed.append(path)
```
This detects files present in the prior run's snapshot that have since been removed from the
install manifest. `TestSubsequentRun` only exercises the "checksum changed" path (line 55),
not the "path deleted" path (line 59). The behavior is correct but untested.

**Fix:** Add a test case in `TestSubsequentRun` that removes an entry from
`state_with_manifest.install_manifest` between run001 and run002 and asserts the removed
path appears in `artifacts_changed`.

---

_Reviewed: 2026-06-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
