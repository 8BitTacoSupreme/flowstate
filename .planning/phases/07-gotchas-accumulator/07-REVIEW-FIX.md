---
phase: 07-gotchas-accumulator
fixed_at: 2026-06-08T23:59:00Z
review_path: .planning/phases/07-gotchas-accumulator/07-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 07: Code Review Fix Report

**Fixed at:** 2026-06-08T23:59:00Z
**Source review:** .planning/phases/07-gotchas-accumulator/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (CR-01, CR-02, WR-01, WR-02, WR-03, WR-04, IN-01, IN-02 — IN-03 addressed under CR-01)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: Z-suffix UTC timestamps not normalized

**Files modified:** `flowstate/gotchas.py`, `tests/test_gotchas.py`
**Commit:** e4a7399
**Applied fix:** Changed `|Z)` to `|[Zz])` in the ISO timestamp regex in `_normalize()`. After
`s.lower()`, the `Z` suffix becomes `z`, so the original literal `Z` never matched. The fix
mirrors the existing `[Tt]` case-insensitive handling for the date-time separator. Added two
tests: `test_replaces_iso_timestamp_z_suffix` (asserts `<ts>` placeholder present and date
digits stripped) and `test_z_and_offset_timestamp_same_sig` (asserts Z-suffix and `+00:00`
messages produce the same signature). Covers IN-03 (missing Z-suffix test) in the same commit.

---

### CR-02: repair command mislabels gotchas source="doctor"

**Files modified:** `flowstate/cli.py`, `tests/test_cli.py`
**Commit:** fc55929
**Applied fix:** Changed `source="doctor"` to `source="repair"` in the repair command's capture
block only (lines ~892-894 in cli.py). The doctor command's block is unchanged. Updated the
existing `test_repair_captures_error_and_warning_findings` test to assert `"repair" in sources`
and `"doctor" not in sources`, replacing the old incorrect assertion that expected `"doctor"`.

---

### WR-01: _rewrite_gotchas_md secondary sort ascending on last_seen

**Files modified:** `flowstate/gotchas.py`
**Commit:** 1ce095b
**Applied fix:** Replaced the single-pass `sort(key=lambda e: (-count, last_seen), reverse=False)`
with a two-pass stable sort matching `context_prefix.py`'s `_read_gotchas_layer`:
first sort by `last_seen desc`, then stable sort by `count desc`. GOTCHAS.md ranking now
matches the context prefix layer ordering.

---

### WR-02: gotchas list CLI secondary sort ascending on last_seen

**Files modified:** `flowstate/cli.py`
**Commit:** 0a790ac
**Applied fix:** Applied the identical two-pass stable sort fix to the `gotchas list` CLI command.
All three ranking paths (GOTCHAS.md, context prefix layer, CLI list) now agree.

---

### WR-03: Dedup scan misses existing gotchas at scale / WR-04: prune accesses _conn directly

**Files modified:** `flowstate/memory.py`, `flowstate/gotchas.py`, `flowstate/cli.py`,
`tests/test_gotchas.py`, `tests/test_memory.py`
**Commit:** 240f9ad
**Applied fix (WR-03):** Added `MemoryStore.get_gotchas()` — a SQL query with a parameterized
`tags LIKE '%"gotcha"%'` filter that returns ALL gotcha-tagged INSIGHT entries without competing
with the shared `kind` limit. Updated `capture_gotcha` dedup scan, `_rewrite_gotchas_md`,
`gotchas list`, and `gotchas prune` to use `get_gotchas()` instead of `get_by_kind(INSIGHT,
limit=N)`. Also updated two `TestNeverRaises` mocks from `get_by_kind` to `get_gotchas`.
Added test: `test_dedup_survives_many_non_gotcha_insight_entries` — inserts 510 non-gotcha
INSIGHT entries then verifies re-capturing an existing gotcha produces count=2 not duplicate.
**Applied fix (WR-04):** Added `MemoryStore.delete(memory_id: str) -> None` — parameterized
`DELETE FROM memories WHERE id=?` with commit; the `memories_ad AFTER DELETE` trigger keeps
FTS in sync. Changed `gotchas prune` to call `store.delete(entry.id)` instead of
`store._conn.execute(...)`. Removed now-unused `MemoryKind` import from the prune command.
Added `test_get_gotchas_returns_only_gotcha_tagged_insight`, `test_delete_removes_entry`, and
`test_delete_nonexistent_is_noop` in test_memory.py.

---

### IN-01: build_context_prefix docstring says "four layers"

**Files modified:** `flowstate/context_prefix.py`
**Commit:** 71930c7
**Applied fix:** Updated docstring from "Composes four layers in most-stable-first order:
fixtures → pack (if it fits) → memory → since-last-run" to "Composes five layers in
most-stable-first order: fixtures → pack (if it fits) → gotchas → memory → since-last-run".

---

### IN-02: _parse_frontmatter parses body when closing --- is absent

**Files modified:** `flowstate/gotchas.py`, `tests/test_gotchas.py`
**Commit:** c980b15
**Applied fix:** Added a `closed` flag and `i > 20` guard inside the loop. The function now
returns `result if closed else {}` — only returning parsed key/value pairs when a closing `---`
delimiter was actually found. An unclosed opening `---` returns `{}`. Updated the existing
`test_malformed_no_closing_dashes` test to assert `result == {}` (was loose `isinstance` check).
Added `test_unclosed_frontmatter_does_not_parse_body` to verify body `status: see above` lines
are not returned as frontmatter.

---

## Skipped Issues

None — all 7 in-scope findings were fixed.

---

## Verification Results

All checks run from worktree before fast-forward merge:

```
pytest:      510 passed, 4 warnings — 92.18% coverage (required ≥80%)
ruff check:  All checks passed
ruff format: 56 files already formatted
bridge imports in gotchas.py:        0
bridge imports in context_prefix.py: 0
yaml import in gotchas.py:           0
```

---

_Fixed: 2026-06-08T23:59:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
