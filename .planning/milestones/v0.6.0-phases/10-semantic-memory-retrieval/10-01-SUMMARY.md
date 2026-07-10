---
phase: 10-semantic-memory-retrieval
plan: "01"
subsystem: memory
status: complete
tags: [semantic-retrieval, knn, sqlite-vec, memory, fts5-fallback]
dependency_graph:
  requires: [phase-09-vec0-foundation]
  provides: [semantic-knn-get-context]
  affects: [context_prefix, all-callers-of-get-context]
tech_stack:
  added: []
  patterns: [KNN-then-FTS5-fallback, FTS5-relevance-gate]
key_files:
  created: []
  modified:
    - flowstate/memory.py
    - tests/test_memory.py
decisions:
  - "_SEMANTIC_K set to 10 (not plan's suggested 5) to match FTS5 limit=10 for token-count parity in compound-eval enrichment axis"
  - "FTS5 relevance gate added inside _semantic_results: KNN only fires when FTS5 finds at least one match, preserving no-match -> empty contract"
metrics:
  duration_seconds: 673
  completed_date: "2026-06-18"
  tasks_completed: 2
  files_modified: 2
requirements: [MEM-01, MEM-02]
---

# Phase 10 Plan 01: Semantic KNN in get_context Summary

Wired semantic KNN retrieval (memories_vec + sqlite-vec) into `MemoryStore.get_context()` with a byte-identical FTS5/BM25 fallback and never-raises contract.

## What Was Built

### Task 1: Semantic KNN in get_context with FTS5 fallback (flowstate/memory.py)

Added `_SEMANTIC_K = 10` module constant and a private `_semantic_results(self, query, k)` helper that:
- Returns `None` (fall back) when `_vec_ready` is False or embedder unavailable
- Runs an FTS5 relevance gate (`search(query, limit=1)`) — returns None if no lexical match, preserving the existing "no-match -> ''" contract
- Embeds the query via `self._embedder.embed([query])`, serializes with `sqlite_vec.serialize_float32`
- Issues `SELECT rowid, distance FROM memories_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?`
- Maps rowids back via `SELECT * FROM memories WHERE rowid=?` + `_row_to_entry`
- Returns `list[SearchResult]` preserving KNN distance order, or None on any failure
- Entire body wrapped in `try/except Exception: return None` (T-10-01, T-10-02)

Updated `get_context` to call `_semantic_results` first; falls back to `self.search(query, limit=10)` when None is returned. The existing char-budget trimming loop is untouched.

### Task 2: Offline tests — TestGetContextSemantic (tests/test_memory.py)

Added 5 tests in `TestGetContextSemantic`:
- `test_semantic_ordering_differs_from_bm25`: hand-chosen vectors ensure "beta" memory is KNN-nearest while "alpha" is BM25-top; asserts semantic path returns beta first
- `test_byte_identity_fallback`: two stores with `_unavailable_embedder()` produce identical `get_context` output (exact `==`)
- `test_knn_failure_falls_back_to_fts5_no_raise`: forces embed to raise after warm-up; confirms FTS5 fallback fires without propagating exception
- `test_empty_store_returns_empty_string_semantic`: empty store returns `""` on both paths
- `test_no_match_returns_empty_string_semantic`: empty store + no-match returns `""`

All vec-dependent tests carry `@pytest.mark.skipif(not _HAS_VEC, ...)`. No network/model downloads.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] _SEMANTIC_K changed from 5 to 10 for compound-eval enrichment parity**
- **Found during:** Task 1 GREEN phase verification
- **Issue:** With k=5, `test_cheap_dry_all_four_axes_show_movement` failed because prefix_tokens peaked then declined (956->1109->1200->1095->1021). KNN returning 5 results vs FTS5's 10 caused the combined enrichment score to be "flat" (delta < 10% threshold).
- **Fix:** Changed `_SEMANTIC_K = 10` to match FTS5's `limit=10`. The char-budget loop in `get_context` is the effective precision control anyway — k=10 gives the same candidate pool as FTS5.
- **Files modified:** flowstate/memory.py (constant only)
- **Commit:** 3c6fd3e

**2. [Rule 1 - Bug] Added FTS5 relevance gate inside _semantic_results**
- **Found during:** Task 1 GREEN phase verification (after implementing _semantic_results)
- **Issue:** `TestGetContext::test_get_context_empty_on_no_match` failed because fastembed IS installed in the test environment, so `available()=True` and KNN fired for "nonexistent_xyzzy" — returning the k nearest vectors even though no FTS5 match existed. KNN has no "no-match" concept.
- **Fix:** Added `if not self.search(query, limit=1): return None` as a relevance gate. When FTS5 finds nothing, KNN is suppressed and the existing FTS5 empty-return path fires.
- **Files modified:** flowstate/memory.py (_semantic_results body)
- **Commit:** 3c6fd3e

## Verification Results

- `ruff check flowstate/memory.py tests/test_memory.py`: clean
- `ruff format --check flowstate/memory.py tests/test_memory.py`: clean
- `pytest tests/ --cov=flowstate --cov-fail-under=80 -q`: 744 passed, coverage 92.41%
- `grep "ORDER BY distance LIMIT" flowstate/memory.py`: line 518 (inside `_semantic_results`)
- `grep "self.search(query, limit=10)" flowstate/memory.py`: line 543 (fallback in `get_context`)
- All 3 existing `TestGetContext` golden tests pass unmodified
- `TestGetContextSemantic`: 5 new tests pass (1 skips when sqlite_vec absent)
- Bench compound test `test_cheap_dry_all_four_axes_show_movement`: passes

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes. The KNN query uses bound parameters only (serialized blob + integer k) — T-10-01 SQL injection mitigation confirmed. The `try/except Exception: return None` never-raises contract covers T-10-02 (KNN failure DoS path). No new threat surface beyond the plan's threat model.

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/10-semantic-memory-retrieval/10-01-SUMMARY.md`
- RED commit 172da97 exists
- GREEN commit 3c6fd3e exists
- 744 tests pass, coverage 92.41%
