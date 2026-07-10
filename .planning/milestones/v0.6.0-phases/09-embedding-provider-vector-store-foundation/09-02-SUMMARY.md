---
phase: 09-embedding-provider-vector-store-foundation
plan: "02"
subsystem: memory
status: complete
tags: [sqlite-vec, vec0, vector-store, memory, embeddings, tdd]
dependency_graph:
  requires: [09-01]
  provides: [10-01, 11-01]
  affects: [flowstate/memory.py, tests/test_memory.py]
tech_stack:
  added: []
  patterns:
    - sqlite-vec vec0 virtual table for dense-vector storage
    - enable_load_extension + re-scope pattern (T-09-03 mitigation)
    - delete-then-insert upsert for vec0 rows (idempotent replace)
    - lazy backfill on MemoryStore open (never-raises, idempotent)
key_files:
  modified:
    - path: flowstate/memory.py
      role: MemoryStore extended with vec0 table, embed-on-write, lazy backfill
    - path: tests/test_memory.py
      role: offline vec0 tests via fake embedder + _HAS_VEC skipif guard
decisions:
  - "Rowid resolution via SELECT rowid FROM memories WHERE id=? (not cursor.lastrowid) — uniform across add/update/add_many, no signature change required"
  - "dim derived from embedder.dim at open time; CREATE TABLE IF NOT EXISTS is idempotent, so existing tables keep their dim on reopen"
  - "enable_load_extension(False) immediately after sqlite_vec.load() — re-scopes the extension-load surface per T-09-03"
  - "_unavailable_embedder() helper added to tests to simulate fastembed absent without depending on its absence in the venv"
  - "Backfill test uses delete-from-memories_vec to simulate un-vectored rows; avoids dim mismatch caused by two opens with different dims"
metrics:
  duration_seconds: 420
  completed_date: "2026-06-18"
  tasks_completed: 2
  files_modified: 2
---

# Phase 09 Plan 02: Vector Store Foundation Summary

sqlite-vec vec0 backing table wired into MemoryStore — embed-on-write (add/update/add_many), lazy backfill on open, embedder injection seam, full degradation to FTS5-only when sqlite-vec or embedder absent.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Load sqlite-vec, create memories_vec, embed on add/update/add_many | ac6eff2 (RED), 44836c7 (GREEN) | flowstate/memory.py, tests/test_memory.py |
| 2 | Lazy backfill on open + tests (fake embed_fn, skipif sqlite_vec) | 44836c7 | flowstate/memory.py, tests/test_memory.py |

## What Was Built

### flowstate/memory.py

Extended `MemoryStore` additively — no existing behavior changed, no state.py touched.

**`__init__`**: gains `embedder: Embedder | None = None` keyword-only param. Injected embedder is used directly; `None` falls through to `get_embedder(root)` (fastembed-optional). Calls `_init_vec()` then `_backfill_vectors()` after schema setup.

**`_init_vec()`**: `enable_load_extension(True)` → `sqlite_vec.load(conn)` → `enable_load_extension(False)` (T-09-03 re-scope) → `CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(embedding float[D])`. Any failure sets `_vec_ready = False`; never raises.

**`_embed_rowid(rowid, text)`**: guarded by `_vec_ready and embedder.available()`. delete-then-insert upsert: `DELETE FROM memories_vec WHERE rowid=?` then `INSERT ... serialize_float32(...)`. Entire helper wrapped never-raises.

**`_backfill_vectors()`**: selects `rowid NOT IN (SELECT rowid FROM memories_vec)`, calls `_embed_rowid` per row, commits once. Never raises, never blocks.

**`add/update/add_many`**: after the existing INSERT/UPDATE + commit, resolve rowid via `SELECT rowid FROM memories WHERE id=?` then call `_embed_rowid`. `add()` return type (entry.id) unchanged.

### tests/test_memory.py

Added `_HAS_VEC` skipif guard (mirrors bench/grounding.py), `_fake_embedder(dim=4)` factory, `_unavailable_embedder()` for testing absent-embedder paths without depending on fastembed being uninstalled.

`TestMemoriesVecTable` (10 tests): table creation, add/add_many/update vec row counts, load_extension re-scope verification, `_vec_ready` flag.

`TestLazyBackfill` (3 tests): backfill on reopen, idempotency, absent-embedder noop.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] noqa directive for non-enabled rule**
- **Found during:** Task 1 ruff check
- **Issue:** `# noqa: PLC0415` on local sqlite_vec imports — PLC0415 is not in ruff's selected ruleset for this project
- **Fix:** Replaced with descriptive inline comments
- **Files modified:** flowstate/memory.py

**2. [Rule 1 - Bug] Unused counter variable in _fake_embedder**
- **Found during:** RED phase ruff pre-commit check
- **Issue:** `counter = [0]` leftover from draft; ruff F841
- **Fix:** Removed the unused variable
- **Files modified:** tests/test_memory.py

**3. [Rule 1 - Bug] pytest.raises(Exception) caught by ruff B017**
- **Found during:** RED phase ruff pre-commit check
- **Issue:** B017 — blind exception catch in `pytest.raises`
- **Fix:** Changed to `pytest.raises((sqlite3.OperationalError, AttributeError))` then refined to `pytest.raises(sqlite3.OperationalError)` — `load_extension()` raises OperationalError after `enable_load_extension(False)`
- **Files modified:** tests/test_memory.py

**4. [Rule 1 - Bug] Test assumptions required fastembed absent; venv has fastembed**
- **Found during:** GREEN phase (test_add_without_embedder, test_backfill_on_reopen_with_embedder)
- **Issue:** Tests using `MemoryStore(root=tmp_path)` (no explicit embedder) expected zero vec rows, but fastembed is installed in the venv so rows were written
- **Fix:** Added `_unavailable_embedder()` helper (sets `_unavailable = True` directly on Embedder) and used it for "embedder absent" test paths; backfill test uses delete-from-memories_vec to simulate un-vectored rows within a consistent dim
- **Files modified:** tests/test_memory.py

## Threat Surface Scan

T-09-03 (Elevation of Privilege via enable_load_extension): mitigated — `enable_load_extension(False)` called immediately after `sqlite_vec.load()`. Verified by `test_load_extension_disabled_after_load`: `load_extension()` raises `OperationalError` after the re-scope.

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond those documented in the plan's threat model.

## Known Stubs

None. The vec0 table is fully wired for write + backfill. Semantic KNN retrieval in `get_context()` is intentionally deferred to Phase 10 (out of scope for this plan).

## Verification Results

- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q`: 730 passed, 92.41% coverage
- `memories_vec` table present after open (sqlite_vec installed): confirmed
- `enable_load_extension(False)` called after load: confirmed by test
- `state.py` untouched: confirmed (`git diff --name-only flowstate/state.py` empty)
- `ruff check + ruff format`: clean on both modified files
- `add()` return type unchanged: confirmed

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | ac6eff2 | PASSED — 9 failing tests confirmed |
| GREEN (feat) | 44836c7 | PASSED — 730 tests, all passing |

## Self-Check: PASSED

- [x] flowstate/memory.py modified with vec0 support
- [x] tests/test_memory.py extended with 13 new vec tests
- [x] Commits ac6eff2 and 44836c7 exist
- [x] 730 tests pass at 92.41% coverage
