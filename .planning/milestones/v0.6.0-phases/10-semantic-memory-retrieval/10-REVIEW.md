---
phase: 10-semantic-memory-retrieval
reviewed: 2026-06-18T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - flowstate/memory.py
  - tests/test_memory.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 10 wires semantic KNN retrieval into `MemoryStore.get_context()` with an FTS5 fallback. The
mechanical port of the bench `_retrieve_vec` KNN query is correct and well-parameterized (no SQL
injection), the never-raises degradation contract is intact, and the byte-identity fallback path is
genuinely unchanged. Tests are mostly meaningful and run offline.

**However, the headline deviation — the "FTS5 relevance gate" (`if not self.search(query, limit=1):
return None`) — is a correctness defect against the milestone's own requirements and silently
defeats the proven value of this phase.** It makes semantic retrieval a strict *subset* of lexical
retrieval: KNN can only fire on queries that FTS5 already matches. The entire reason this milestone
exists — surfacing the semantically-relevant memory that BM25 *misses* (bench: right article 17/20
semantic vs 3/20 lexical) — is exactly the case the gate suppresses. This is the milestone's value
proposition inverted, and it also instantiates the precise pattern REQUIREMENTS.md lists as Out of
Scope ("hybrid lexical+semantic fusion").

The good news: the underlying problem the gate solves is real, and there is a correct, in-scope fix.

---

## Headline Verdict: Replace the FTS5 Gate with a KNN Distance Threshold

**Severity: CRITICAL (CR-01).** The FTS5 gate must go. The correct replacement is a distance/
similarity threshold on the KNN results themselves.

Reasoning against the four sub-questions in scope:

1. **Violates MEM-01.** MEM-01: "`get_context()` returns semantic-KNN-ranked memories when vectors
   and an embedder are available." The gate adds a lexical precondition found nowhere in the spec:
   memories are returned by KNN *only if FTS5 already matched*. When the embedder is available and
   vectors exist but FTS5 finds nothing, the function returns `""` — not KNN-ranked memories. The
   contract is conditioned on a lexical gate the requirement never authorizes.

2. **It IS the out-of-scope pattern.** REQUIREMENTS.md "Out of Scope" explicitly lists *"Reranking /
   hybrid lexical+semantic fusion"* with the rationale "Pure semantic KNN already recovered
   oracle-level grounding... fusion is unjustified complexity until measured to help." `search(query)
   AND knn(query)` is precisely a lexical+semantic conjunction — a fusion gate. The phase shipped the
   one composition the milestone forbade. The SUMMARY even names the pattern in its own frontmatter
   (`patterns: [..., FTS5-relevance-gate]`), so this is a documented, deliberate scope breach, not an
   accident.

3. **It compromises the proven win.** The bench result that justifies this entire milestone:
   FTS5 retrieves the *wrong* article (or nothing) while semantic retrieves the *right* one because
   "lexical density ≠ fact location." The win lives entirely in the lexically-disjoint-but-
   semantically-relevant region. The gate's `limit=1` check requires at least one lexical token
   match before KNN runs — so for any query whose vocabulary differs from the stored memory's
   vocabulary (the exact 17/20-vs-3/20 case), the gate returns `None` and falls back to the empty
   FTS5 result. The phase preserves semantic retrieval *only* for queries BM25 could already serve,
   and discards it for the queries that motivated the work. Net effect on the proven win: broken.

4. **A distance threshold is the correct, in-scope fix.** The real problem is legitimate: vec0 KNN
   is unconditional nearest-k, so `get_context("nonexistent_xyzzy")` returns the k nearest vectors
   (noise) instead of `""`. The right fix is to reject KNN hits whose distance exceeds a relevance
   cutoff — a property of the *semantic* signal itself, not a lexical crutch. Feasibility: the
   embedder is `bge-small-en-v1.5`, and the bench used cosine/L2 over its 384-dim outputs with
   stable, separable distances (17/20 separation at k=3 implies relevant vs irrelevant distances are
   well-distinguished). vec0's default `vec_distance_cosine` yields cosine *distance* in `[0, 2]`;
   a conservative cutoff (e.g. cosine distance < ~0.6, equivalently cosine similarity > ~0.4) filters
   pure-noise neighbors while keeping the semantically-relevant ones. Implementation is a one-line
   filter on `knn_rows` by `distance`. This keeps the path pure-semantic (in scope), preserves the
   no-match→`""` contract, and does NOT condition the win on lexical overlap.

   Caveat to address during the fix: the threshold value should be calibrated against the bench rig
   (`bench/grounding.py` wikivec arm has the distances) rather than guessed, and it must be derived
   for the actual distance metric vec0 is configured with (confirm cosine vs L2 on the `memories_vec`
   table definition — if L2 over unnormalized vectors, normalize first or the threshold is not
   portable). Until calibrated, a threshold is still strictly more correct than the gate because it
   degrades on the semantic axis instead of the lexical one.

**Do not keep the gate.** It trades a real but narrow bug (KNN noise on no-match) for a defect that
nullifies the phase's purpose and breaches an explicit scope boundary.

---

## Critical Issues

### CR-01: FTS5 relevance gate defeats the semantic win and violates MEM-01 / Out-of-Scope

**File:** `flowstate/memory.py:506-509`
**Issue:** The gate `if not self.search(query, limit=1): return None` makes semantic KNN a subset of
lexical search. It suppresses retrieval for exactly the lexically-disjoint-but-semantically-relevant
queries the milestone exists to serve (bench: 17/20 vs 3/20), violates MEM-01's unconditional
"returns semantic-KNN-ranked memories," and implements the "hybrid lexical+semantic fusion" pattern
that REQUIREMENTS.md lists as Out of Scope. See headline verdict for full reasoning.
**Fix:** Remove the FTS5 gate. Replace with a distance threshold on the KNN rows:
```python
# Remove these two lines:
# if not self.search(query, limit=1):
#     return None
...
knn_rows = self._conn.execute(
    "SELECT rowid, distance FROM memories_vec "
    "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
    (serialized, k),
).fetchall()
# Threshold on the semantic signal itself (calibrate against bench wikivec distances;
# value below assumes cosine distance — confirm the memories_vec distance metric first):
_MAX_SEMANTIC_DISTANCE = 0.6  # cosine distance cutoff; tune on bench rig
knn_rows = [r for r in knn_rows if r[1] <= _MAX_SEMANTIC_DISTANCE]
if not knn_rows:
    return None
```
This preserves the no-match→`""` contract on the semantic axis, keeps the path pure-semantic
(in scope), and does not gate the win on lexical overlap. Calibrate `_MAX_SEMANTIC_DISTANCE` against
`bench/grounding.py` before merge; ship a conservative default if calibration is deferred.

---

## Warnings

### WR-01: Ordering test passes trivially — it does not exercise threshold behavior and overfits the gate

**File:** `tests/test_memory.py:826-908` (`test_semantic_ordering_differs_from_bm25`)
**Issue:** The one test that proves the semantic win uses a query (`"kafka streaming"`) that *also*
lexically matches the `alpha` memory, so it sails through the FTS5 gate. It therefore never exercises
the failure mode the gate introduces (lexically-disjoint query → suppressed KNN). The test green-lit
a design that breaks the actual win. After CR-01 is fixed, this test should be supplemented with a
case where the winning memory shares *zero* query tokens, proving KNN still surfaces it.
**Fix:** Add a test with a query that has no lexical overlap with the semantically-nearest memory
(e.g. query `"zzz"` mapped to `beta_vec`, beta memory content sharing no tokens with the query),
asserting `get_context` still returns beta first. This is the regression guard for CR-01 and the
proof of MEM-01.

### WR-02: `test_no_match_returns_empty_string_semantic` has dead body — does not test the no-match semantic path

**File:** `tests/test_memory.py:1003-1034`
**Issue:** The test sets up a store with one memory and a fake embedder, then the entire setup is
followed by `pass` with a comment admitting "semantic path may return a hit... so test an empty store
variant instead." The only real assertion runs against a *separate empty store*. So the test name
promises "no-match returns empty on the semantic path" but actually only tests an empty store — the
populated no-match case (the one the FTS5 gate was added to handle) is never asserted. The first
store and its `add()` are dead setup. This is the test that should have caught the gate's design cost
and instead it was neutered to pass.
**Fix:** Delete the dead first-store block. Once CR-01 lands a distance threshold, write a real
assertion: populated store + a query whose vector is far from all stored vectors → `get_context`
returns `""`. That genuinely exercises the no-match semantic path.

### WR-03: `_SEMANTIC_K = 10` was changed to make an unrelated compound-eval test pass, not on retrieval merit

**File:** `flowstate/memory.py:8-14` (constant), SUMMARY deviation #1
**Issue:** The plan specified `k=5` (bench range 3–5; bench got 17/20 at k=3). The executor bumped it
to 10 because `test_cheap_dry_all_four_axes_show_movement` failed on a token-count delta threshold —
i.e. k was tuned to satisfy a *token-growth* assertion in a different subsystem, not to improve
grounding. The justification ("char budget is the real limiter") is plausible but undocumented by
measurement, and k=10 doubles the bench-validated neighborhood with no grounding evidence. With a
distance threshold (CR-01) the over-wide k becomes lower-risk (noise neighbors get filtered), but the
value should still be defended on retrieval grounds, not coupled to a compound-eval token assertion.
**Fix:** Either restore `k=5` and adjust the compound-eval test's threshold to reflect reality, or
keep `k=10` with a comment citing a measured grounding comparison. Do not let an enrichment-axis
token-delta test dictate the retrieval neighborhood size.

---

## Info

### IN-01: KNN/BM25 `score` field has inconsistent semantics across the two paths

**File:** `flowstate/memory.py:529` vs `:457`
**Issue:** `search()` populates `SearchResult.score` with `abs(row["rank"])` (a positive BM25
magnitude), while `_semantic_results` populates it with raw KNN `distance` (lower = better). Any
future caller that sorts or compares `SearchResult.score` across the two paths will misbehave.
`get_context` currently ignores `score`, so this is latent, not active.
**Fix:** Document the dual meaning in `SearchResult`, or normalize to a single "higher = more
relevant" convention (e.g. store `-distance` or `1/(1+distance)` on the semantic path).

### IN-02: N+1 query pattern in rowid→entry mapping

**File:** `flowstate/memory.py:524-529`
**Issue:** One `SELECT * FROM memories WHERE rowid=?` per KNN row. Acceptable at this scale (k≤10,
local SQLite) and out of v1 perf scope — flagged only because the plan's interface note suggested a
single `WHERE rowid IN (...)` + re-order. Not a defect.
**Fix:** Optional: batch with `WHERE rowid IN (...)` and re-sort by the KNN order in Python. Low
priority.

### IN-03: Stale comment on default-embedder availability

**File:** `flowstate/memory.py:157`
**Issue:** Comment states the default (`embedder=None`) "produces an Embedder whose available() is
False." With fastembed installed in this environment, `get_embedder(root)` returns an *available*
embedder — which is exactly why the default `store`/`populated_store` fixtures now write real vectors
and the golden no-match test broke (SUMMARY deviation #2). The comment misleads readers about when
the semantic path activates.
**Fix:** Update the comment to: default embedder is available iff the `[semantic]` extra/fastembed is
importable; otherwise `available()` is False and the store is FTS5-only.

---

## Notes (verified, no finding)

- **Byte-identity fallback (MEM-02): genuinely intact.** When `_vec_ready` or `available()` is False,
  `_semantic_results` returns `None` before any vector work and `get_context` runs the unchanged
  `search(query, limit=10)` + verbatim char-budget loop. `test_byte_identity_fallback` and the
  existing `TestGetContext` golden tests confirm.
- **Never-raises contract: intact.** `except Exception: return None` correctly degrades to FTS5.
  Acceptable here (degradation, not masking) because the fallback path is a fully valid result, not a
  swallowed error — consistent with the project's `_retrieve_vec` / `_embed_rowid` convention.
- **SQL injection (T-10-01): mitigated.** Serialized blob and `k` are bound parameters; query text is
  never interpolated.
- **Backward-compat signature:** `get_context(query, *, max_tokens=2000, k=_SEMANTIC_K)` keeps the
  positional `query` + keyword `max_tokens` callers depend on; adding keyword-only `k` is safe.

---

_Reviewed: 2026-06-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
