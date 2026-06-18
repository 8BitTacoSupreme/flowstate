---
phase: 09-embedding-provider-vector-store-foundation
verified: 2026-06-18T00:00:00Z
status: passed
score: 14/14
overrides_applied: 0
---

# Phase 9: Embedding Provider + Vector Store Foundation — Verification Report

**Phase Goal:** The optional embedding layer and its backing vector store exist — semantic vectors can be computed, persisted, and queried when the [semantic] extra is installed, and every path degrades silently to FTS5-only when it is not.
**Verified:** 2026-06-18
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Importing `flowstate.embeddings` succeeds on a bare install without fastembed | VERIFIED | `python -c "import flowstate.embeddings"` exits 0; builtins monkeypatch test passes (`test_import_succeeds_without_fastembed`) |
| 2 | `get_embedder().available()` returns `False` when fastembed is absent and never raises | VERIFIED | `test_available_returns_false_when_fastembed_absent`; blocking import monkeypatch confirms False, not an exception |
| 3 | With injected embed_fn: `available()` is True, `embed(...)` returns correct vectors, `dim` equals vector length | VERIFIED | `test_available_returns_true_with_injected_embed_fn`, `test_embed_returns_fake_vectors_with_injected_fn`, `test_dim_derived_from_injected_fn` |
| 4 | `configured_dim` returns `_DEFAULT_DIM` without constructing or downloading the model | VERIFIED | `test_configured_dim_returns_default_without_model_load`; `e._model is None` and `e._unavailable is False` confirmed by live probe |
| 5 | Model name resolves: env var > `.planning/config.json embed_model` > `BAAI/bge-small-en-v1.5` | VERIFIED | 7 precedence tests in `test_embeddings.py` covering all tiers, fallthrough, and malformed config |
| 6 | fastembed appears only once in `pyproject.toml`, under `[semantic]` extra | VERIFIED | `grep -v '^#' pyproject.toml \| grep -c 'fastembed'` == 1; confirmed at line 32 |
| 7 | `MemoryStore` open on any db creates `memories_vec` vec0 table without a migration command | VERIFIED | `test_memories_vec_created_on_open`, `test_store_opens_on_existing_db_without_migration`; live probe confirms table in on-disk `memory.db` |
| 8 | `add()` with embedder absent writes zero vec rows and does not raise; returns `entry.id` unchanged | VERIFIED | `test_add_without_embedder_writes_zero_vec_rows`, `test_add_returns_entry_id_unchanged`; live probe confirms |
| 9 | `add()` with available embedder writes exactly one `memories_vec` row keyed to the memory rowid | VERIFIED | `test_add_with_embedder_writes_one_vec_row`; rowid confirmed via `SELECT rowid FROM memories WHERE id=?` |
| 10 | `add_many()` vec writes are all-or-nothing (savepoint rollback) | VERIFIED | `SAVEPOINT add_many_vec` and `ROLLBACK TO SAVEPOINT add_many_vec` present in `add_many()` source; `TestWR04AddManyAtomicVec` exercises the rollback path |
| 11 | `update()` re-embeds and replaces the vec row; no-op when embedder absent | VERIFIED | `test_update_replaces_vec_row` confirms exactly one row after update; absent-embedder path is guarded by `_vec_ready and embedder.available()` |
| 12 | Backfill deferred to first write; `__init__` never blocks or downloads model | VERIFIED | `_backfill_pending` flag set in `__init__`; `_backfill_vectors()` is NOT called from `__init__` directly — only via `_maybe_backfill()` on first write; `TestWR01NoModelLoadOnOpen` confirms no `TextEmbedding` constructed during open |
| 13 | Dim mismatch on reopen sets `_vec_ready=False` (FTS5-only) rather than silent divergence | VERIFIED | `_init_vec` parses `sqlite_master.sql` for `float[\d+]` pattern, compares to `configured_dim`; `TestWR02DimMismatch` and live probe confirm |
| 14 | `flowstate/state.py` and `get_context()` (FTS5 path) are additive-only — no Phase-10 KNN leaked | VERIFIED | `git log -- flowstate/state.py` shows no Phase 9 commits; `get_context()` source contains no `knn`/`semantic` references; still calls `self.search()` only |

**Score:** 14/14 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/embeddings.py` | Lazy embedding provider: `get_embedder()`, `embed()`, `dim`, `configured_dim`, `available()` | VERIFIED | 221 lines; all public API present and substantive |
| `pyproject.toml` | `[semantic]` optional extra declaring `fastembed>=0.3` | VERIFIED | Line 32: `semantic = ["fastembed>=0.3"]`; fastembed not in core deps |
| `tests/test_embeddings.py` | 20 offline tests covering import-guard, fake-embed, precedence, caching | VERIFIED | 20 tests, all offline; no fastembed imports at module level |
| `flowstate/memory.py` | `memories_vec` vec0 table, embed-on-write, lazy backfill, `embedder=` injection seam | VERIFIED | Contains `memories_vec`, `_init_vec`, `_embed_rowid`, `_backfill_vectors`, `_maybe_backfill`, `_BACKFILL_BATCH`, `_backfill_pending` |
| `tests/test_memory.py` | vec0 store tests with fake embedder + `_HAS_VEC` skipif guard | VERIFIED | `TestMemoriesVecTable` (10 tests), `TestLazyBackfill` (3 tests), plus `TestCR01`, `TestWR01`–`TestWR05` fix-coverage classes |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `flowstate/memory.py MemoryStore.__init__` | `sqlite_vec.load(self._conn)` | `enable_load_extension(True)` then local `import sqlite_vec` then `sqlite_vec.load` inside `_init_vec` | WIRED | `_init_vec` source confirmed; `finally` re-scopes to False |
| `flowstate/memory.py MemoryStore.add` | `memories_vec INSERT` | `_embed_rowid` → `sqlite_vec.serialize_float32` → INSERT keyed by rowid | WIRED | `serialize_float32` present in `_embed_rowid`; rowid via `SELECT rowid FROM memories WHERE id=?` |
| `flowstate/memory.py MemoryStore.__init__` | `flowstate.embeddings.get_embedder` | Import at top of module; used in `__init__` when `embedder=None` | WIRED | Line 19: `from flowstate.embeddings import Embedder, get_embedder`; used at line 151 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `MemoryStore.add` | `vec` from `embedder.embed(...)` | `Embedder._embed_fn` (injected) or `fastembed.TextEmbedding.embed()` (real) | Yes — serialized via `sqlite_vec.serialize_float32` and persisted to `memories_vec` | FLOWING |
| `MemoryStore._backfill_vectors` | rows from `memories WHERE rowid NOT IN memories_vec` | Live SQLite query; `LIMIT _BACKFILL_BATCH` cap (500) | Yes — queries actual `memories` table; skips already-vectored rows | FLOWING |

---

## Phase Invariants Verification (from code-review round)

| Invariant | Finding | Status |
|-----------|---------|--------|
| `enable_load_extension(False)` in `finally` block | Confirmed in `_init_vec` source: inner `try/finally` wraps `sqlite_vec.load()`; `enable_load_extension(False)` executes on every exit including load failure | VERIFIED |
| `MemoryStore` open with default embedder does NOT construct/download model | `_init_vec` uses `configured_dim` (not `dim`); `configured_dim` returns `_DEFAULT_DIM` (384) without calling `_ensure_model()`; live probe with patched `TextEmbedding` confirms `constructed == []` | VERIFIED |
| Backfill deferred (not blocking `__init__`) | `_backfill_pending` flag set in `__init__`; `_backfill_vectors()` only called via `_maybe_backfill()` in `add`/`add_many`/`update`; `__init__` source confirms no direct call | VERIFIED |
| `memories_vec` keyed to `rowid` on real on-disk `memory.db` | Live probe: table exists in `memory.db` after `MemoryStore` open; vec row `rowid` matches `memories.rowid` | VERIFIED |
| `add()`/`update()`/`add_many()` embed on write when available; silent when absent | All three confirmed by test suite and direct inspection; `add()` still returns `entry.id` | VERIFIED |
| `add_many()` vec writes all-or-nothing (savepoint) | `SAVEPOINT add_many_vec` and `ROLLBACK TO SAVEPOINT add_many_vec` present in source; `TestWR04` exercises rollback path | VERIFIED |
| Dim mismatch on reopen → FTS5-only (`_vec_ready=False`) | `_init_vec` reads `sqlite_master.sql` and compares to `configured_dim`; mismatch sets `_vec_ready = False` and returns immediately; `TestWR02` and live probe confirm | VERIFIED |
| Additive-only: `state.py` untouched, FTS5/`get_context()` unchanged, no Phase-10/11 leakage | `git log -- flowstate/state.py` shows no Phase 9 commits; `get_context()` calls `self.search()` only; no KNN references in `memory.py` | VERIFIED |
| Tests fully offline (fake `embed_fn` + `skipif sqlite_vec`) | `_HAS_VEC` guard on all vec-dependent tests; fake embedder via injected `embed_fn`; no real `TextEmbedding` constructed in any test | VERIFIED |
| Full suite green at ≥80% coverage | `739 passed, 92.41%` confirmed by live run | VERIFIED |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Import without fastembed | `.venv/bin/python -c "import flowstate.embeddings; print('import OK')"` | `import OK` | PASS |
| `available()` returns bool | `.venv/bin/python -c "... assert isinstance(p.available(), bool)"` | True (fastembed installed in venv) | PASS |
| `configured_dim` returns 384 without model load | Live probe: `e = Embedder(...); dim = e.configured_dim` | `384`, `_model is None`, `_unavailable=False` | PASS |
| No model constructed at `MemoryStore` open | Live probe with patched `TextEmbedding` | `constructed == []` | PASS |
| `memories_vec` on real on-disk db with rowid key | Live probe: add entry, check db | `vec_ready=True`, `vec rows=1`, `rowid match=True`, table in on-disk file | PASS |
| `add()` with absent embedder: zero vec rows, no raise, returns `entry.id` | Live probe with `_unavailable=True` embedder | `0 vec rows`, no exception, `result == entry.id` | PASS |
| Dim mismatch on reopen → `_vec_ready=False`, FTS5 continues | Live probe dim=4 then dim=8 | `_vec_ready=False`, `add()` returns `entry.id`, `count()==2` | PASS |
| `fastembed` only once in `pyproject.toml` | `grep -c 'fastembed'` | `1` | PASS |
| Full test suite | `.venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` | `739 passed, 92.41%` | PASS |
| ruff clean | `ruff check + ruff format --check` on both files | `All checks passed!`, `2 files already formatted` | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| EMB-01 | 09-01 | `flowstate/embeddings.py` exposes `embed()`, `dim`, `available()`; import never requires fastembed | SATISFIED | Module exists with all three; import-guard test passes |
| EMB-02 | 09-01 | Model name configurable via env var and config.json; default `BAAI/bge-small-en-v1.5` | SATISFIED | `_resolve_model_name` implements env > config > default; 7 precedence tests |
| EMB-03 | 09-01 | fastembed declared only as `[semantic]` extra; core install dep-free | SATISFIED | `pyproject.toml` line 32; `grep -c 'fastembed'` == 1 |
| EMB-04 | 09-01 | `available()` False when absent; callers degrade without raising | SATISFIED | `_ensure_model()` catches all exceptions; `embed()` returns `[]`; `configured_dim` returns `_DEFAULT_DIM` |
| VEC-01 | 09-02 | `memory.db` gains `vec0` virtual table keyed to memory rows; sqlite-vec loaded on `MemoryStore._conn` | SATISFIED | `memories_vec` created in `_init_vec`; live probe confirms on-disk table |
| VEC-02 | 09-02 | `add()`/`update()`/`add_many()` persist embeddings when available; silent FTS5-only when absent | SATISFIED | All three methods call `_embed_rowid` or savepoint path; guarded by `_vec_ready and embedder.available()` |
| VEC-03 | 09-02 | Existing un-vectored rows lazily backfilled on open; open never blocks or fails when embedder absent | SATISFIED | Backfill deferred via `_backfill_pending` to first write; `configured_dim` prevents model load at open; `_BACKFILL_BATCH=500` caps unbounded scan |

All 7 Phase 9 requirements (EMB-01 through EMB-04, VEC-01 through VEC-03) satisfied.

---

## Anti-Patterns Found

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `flowstate/memory.py:228–229` | `import sqlite_vec` local re-import inside `_embed_rowid` | INFO | Intentional: sqlite_vec must be loaded on the connection first; comment explains this |
| `flowstate/memory.py:380` | `import sqlite_vec` local re-import inside `add_many` savepoint block | INFO | Same intentional pattern as above |
| `tests/test_memory.py:30` | `hash(t)` in `_fake_embedder` is non-deterministic across processes (IN-02 from review) | INFO | All current tests assert row counts only; no vector-value assertions; not a blocker |

No TBD/FIXME/XXX/PLACEHOLDER markers in Phase 9 modified files. No stub implementations (all returns are substantive). No hardcoded empty data flowing to visible output.

---

## Human Verification Required

None. All must-haves are verifiable programmatically. The phase goal is fully confirmed by code inspection, live probes, and the test suite.

---

## Gaps Summary

None. All 14 observable truths verified. All 7 requirements satisfied. The critical issue (CR-01) and all 5 warnings from the code review round have been addressed in the final codebase:

- **CR-01 (fixed):** `enable_load_extension(False)` is now in a `finally` block inside `_init_vec`, confirmed by source inspection and `TestCR01ExtensionRescope`.
- **WR-01 (fixed):** `_init_vec` uses `configured_dim` (not `dim`), which never calls `_ensure_model()`; live probe with patched `TextEmbedding` confirms zero constructions at open time.
- **WR-02 (fixed):** Dim mismatch detected via `sqlite_master.sql` parse; `_vec_ready=False` on mismatch; `TestWR02DimMismatch` confirms.
- **WR-03 (fixed):** `_embed_rowid` catches `sqlite3.Error` specifically and flips `_vec_ready=False`; `TestWR03NarrowExcept` confirms.
- **WR-04 (fixed):** `add_many` uses a SAVEPOINT to make all vec writes atomic; `TestWR04AddManyAtomicVec` confirms rollback behavior.
- **WR-05 (fixed):** `_BACKFILL_BATCH=500` limits the backfill SELECT; `TestWR05BackfillBatchLimit` confirms the cap; backfill deferred to first write via `_backfill_pending`.

---

_Verified: 2026-06-18_
_Verifier: Claude (gsd-verifier)_
