---
phase: 09-embedding-provider-vector-store-foundation
fixed_at: 2026-06-18T12:50:00Z
review_path: .planning/phases/09-embedding-provider-vector-store-foundation/09-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-06-18T12:50:00Z
**Source review:** .planning/phases/09-embedding-provider-vector-store-foundation/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, WR-01..WR-05)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: `enable_load_extension(True)` stays ON when `sqlite_vec.load()` raises

**Files modified:** `flowstate/memory.py`, `tests/test_memory.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** Wrapped `import sqlite_vec` + `sqlite_vec.load(self._conn)` in a nested
`try/finally` inside `_init_vec`. The outer `try` catches any exception and sets
`_vec_ready = False`; the inner `finally` calls `enable_load_extension(False)`
unconditionally — even when `.load()` raises. Previously this call sat *after* `.load()`
on the happy path only, leaving the connection with extension-loading enabled on failure.
Test `TestCR01ExtensionRescope.test_extension_disabled_after_load_failure` injects a fake
`sqlite_vec` whose `.load()` raises and asserts the connection refuses `load_extension()`.

### WR-01: `MemoryStore.__init__` constructs/downloads the real model at open time

**Files modified:** `flowstate/embeddings.py`, `flowstate/memory.py`, `tests/test_memory.py`, `tests/test_embeddings.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** Added `Embedder.configured_dim` property that returns `_DEFAULT_DIM` (384)
without calling `_ensure_model()` when no `embed_fn` is injected — pure constant, no fastembed
import or model construction. `_init_vec` now calls `self._embedder.configured_dim` instead
of `self._embedder.dim`. Since `bge-small-en-v1.5` IS 384 dimensions, the table is sized
correctly without any model load. Backfill is additionally deferred out of `__init__` to
`_maybe_backfill()` (called on first write), so read-only paths (count, last_entry_at,
search) never trigger embed work. Tests assert `TextEmbedding` is never constructed during
`MemoryStore(root)` open.

### WR-02: dim mismatch between existing vec0 table and new embedder silently drops all vectors

**Files modified:** `flowstate/memory.py`, `tests/test_memory.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** After `sqlite_vec.load()` succeeds, `_init_vec` queries `sqlite_master`
for the existing `memories_vec` SQL definition and parses the `float[N]` dimension.
If `N != configured_dim`, sets `_vec_ready = False` and returns — store operates in
FTS5-only mode rather than silently producing a diverged index. Test
`TestWR02DimMismatch.test_dim_mismatch_on_reopen_sets_vec_not_ready` creates a dim=4
store, reopens with a dim=8 embedder, and asserts `_vec_ready is False` while confirming
`add()` and `search()` still work via FTS5.

### WR-03: blanket `except Exception: pass` in `_embed_rowid` masks all write failures

**Files modified:** `flowstate/memory.py`, `tests/test_memory.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** Changed `except Exception: pass` in `_embed_rowid` to
`except sqlite3.Error: self._vec_ready = False`. Hard database errors (dim mismatch,
disk-full, locked db) now flip `_vec_ready` to False so subsequent writes stop pretending
to succeed. Embedder-level failures (`embed()` returning `[]`) remain silent no-ops.
Test `TestWR03NarrowExcept` injects a wrong-dim embed_fn into a running store (float[8]
vector into a float[4] table) and asserts `_vec_ready` is flipped while `add()` does
not raise and FTS5 search still returns results.

### WR-04: `_embed_rowid` writes are not committed by `add_many` per-row, and partial-failure leaves divergence

**Files modified:** `flowstate/memory.py`, `tests/test_memory.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** `add_many` now performs all vec writes inside a `SAVEPOINT add_many_vec`.
If any INSERT raises (dim error, disk error), the savepoint is rolled back — zero vec rows
from that call are persisted, preventing partial divergence between `memories` and
`memories_vec`. `_vec_ready` is set False on failure. Memory rows (committed before the
savepoint) are unaffected. Test `TestWR04AddManyAtomicVec` injects a mixed embed_fn that
produces correct dim=4 on the first call and wrong dim=8 on subsequent calls, forcing a
partial failure mid-loop, and asserts all vec rows are rolled back and reconciled on reopen.

### WR-05: `_backfill_vectors` is unbounded — embeds the entire un-vectored table synchronously on open

**Files modified:** `flowstate/memory.py`, `tests/test_memory.py`
**Commit:** fc25eb0 (source), 00e77f8 (tests)
**Applied fix:** Two changes combined:
1. `_backfill_vectors` now adds `LIMIT ?` using class constant `_BACKFILL_BATCH = 500`,
   capping the per-call row scan at 500 rows.
2. Backfill is deferred out of `__init__` entirely — `_backfill_pending` flag is set True
   when `_vec_ready` is True, and `_maybe_backfill()` is called at the top of `add()`,
   `update()`, and `add_many()`. Read-only paths (count, search, last_entry_at, status)
   never trigger backfill or model load.
Test `TestWR05BackfillBatchLimit` patches `_BACKFILL_BATCH = 2` and confirms at most
3 rows are vectored per open on a 5-row un-vectored store.

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-06-18T12:50:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
