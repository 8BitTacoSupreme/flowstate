---
phase: 10-semantic-memory-retrieval
fixed_at: 2026-06-18T00:00:00Z
review_path: .planning/phases/10-semantic-memory-retrieval/10-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-06-18
**Source review:** .planning/phases/10-semantic-memory-retrieval/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, WR-01, WR-02, WR-03, IN-03)
- Fixed: 5
- Skipped: 0

## Fixed Issues

### CR-01: FTS5 relevance gate replaced with L2 distance threshold

**Files modified:** `flowstate/memory.py`
**Commit:** 9f83f8c
**Applied fix:** Removed the two-line FTS5 gate (`if not self.search(query, limit=1): return None`)
from `_semantic_results`. Replaced with a distance filter on `knn_rows`: only neighbors with
`distance <= _SEMANTIC_MAX_DISTANCE` are kept; if none remain, returns `None` (→ FTS5 fallback → "").

**Calibration (empirical, BAAI/bge-small-en-v1.5, vec0 default L2 metric):**
- vec0 default distance confirmed as L2 (tested against known vectors)
- bge-small-en-v1.5 produces unit-normalized embeddings (norm=1.000000)
- Related pairs (lexically disjoint, semantically related): L2 ∈ [0.495, 0.882]
- Unrelated pairs (nonsense tokens / truly disjoint domains): L2 ∈ [0.899, 1.066]
- Gap between max related (0.882) and min unrelated (0.899): ~0.017
- Chosen threshold: **`_SEMANTIC_MAX_DISTANCE = 0.89`** (midpoint; admits all related, rejects all unrelated including the golden "nonexistent_xyzzy" test case)
- Cosine equivalence: L2=0.89 ≈ cosine_distance=0.396 (cosine_sim≈0.604)
- Constant defined at module level with metric, calibration method, and cosine equivalence documented

### WR-01: Ordering test rewritten with lexically-disjoint query

**Files modified:** `tests/test_memory.py`
**Commit:** f6009c4
**Applied fix:** Replaced the trivially-passing `test_semantic_ordering_differs_from_bm25` with a
test that proves the milestone's core value. New design:
- Query text `"zephyr concept"` has **zero token overlap** with beta memory content
  (`"database persistence retrieval storage"`) — FTS5 cannot find beta
- Fake embedder places beta nearest to query (L2≈0.14, within threshold)
- Fake embedder places alpha far from query (L2≈1.62, filtered by threshold)
- Asserts: semantic path returns beta first (lexically-disjoint win); BM25 path returns alpha
  first (keyword match on "zephyr" in alpha content); orderings differ
- This is the regression guard for CR-01: removing the gate now means the test proves the
  win rather than green-lighting a broken gate

### WR-02: Dead-body no-match test replaced with real assertion

**Files modified:** `tests/test_memory.py`
**Commit:** f6009c4
**Applied fix:** Deleted the dead first-store block (populated store + `pass` comment). The new
test uses a populated store with a real distance-threshold assertion:
- Two orthogonal 4-dim unit vectors for stored content vs query (L2 = sqrt(2) ≈ 1.414)
- Inline assertion verifies expected_l2 > `_SEMANTIC_MAX_DISTANCE` (self-documenting)
- `store.get_context("xyzzy_nomatch_far")` must return `""` because all KNN hits exceed the
  threshold → `_semantic_results` returns `None` → FTS5 fallback finds no lexical match → `""`
- Exercises the exact path CR-01 fixed: threshold filter → None → FTS5 fallback

### WR-03: k=10 documented on retrieval grounds

**Files modified:** `flowstate/memory.py`
**Commit:** 9f83f8c
**Applied fix:** Replaced the comment that tied k=10 to "compound-eval token-count parity" with a
retrieval-grounded rationale: k=10 matches the FTS5 candidate pool (limit=10) and the char budget
is the real downstream limiter anyway. Bench validated k=3 for grounding precision; 10 is a
conservative candidate pool, not a tuning for a token-delta test. The value remains 10 — the
compound-eval test (`test_cheap_dry_all_four_axes_show_movement`) confirmed still passing at k=10
with the distance threshold in place.

### IN-03: Stale comment on default-embedder availability updated

**Files modified:** `flowstate/memory.py`
**Commit:** 9f83f8c
**Applied fix:** Updated the comment at `MemoryStore.__init__` from "produces an Embedder whose
`available()` is False when fastembed is absent" to "available iff the `[semantic]` extra /
fastembed is importable; otherwise `available()` is False and the store is FTS5-only." This
accurately reflects the environment where fastembed IS installed and the semantic path fires.

---

## Post-fix Test Results

```
744 passed, 4 warnings in 80.47s
Required test coverage of 80% reached. Total coverage: 92.44%
```

Key tests verified green:
- `test_get_context_empty_on_no_match` (golden no-match test — "nonexistent_xyzzy" → "")
- `test_semantic_ordering_differs_from_bm25` (lexically-disjoint ordering regression guard)
- `test_no_match_returns_empty_string_semantic` (populated-store distance-threshold path)
- `test_byte_identity_fallback` (MEM-02 byte-identity)
- `test_knn_failure_falls_back_to_fts5_no_raise` (never-raises contract)
- `test_cheap_dry_all_four_axes_show_movement` (enrichment axis with k=10)

---

_Fixed: 2026-06-18_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
