---
phase: 11-semantic-wiki-retrieval
reviewed: 2026-06-18T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - flowstate/context_prefix.py
  - tests/test_context_prefix.py
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-18
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 11 adds per-run semantic top-k retrieval to the opt-in `wiki` layer of
`build_context_prefix`, porting the proven bench `_retrieve_vec` KNN mechanics into
`_semantic_wiki_layer`, with a config/env-driven `_load_wiki_k` and a never-raises static
fallback to `_read_wiki_layer`.

The implementation is correct on every high-priority axis and does NOT reproduce either
prior-phase defect class:

- **WIKI-02 byte-identity (verified):** The wiki branch is gated strictly by
  `include_layers is not None and "wiki" in include_layers` and is deliberately kept
  outside the `_included()` helper. The default (`include_layers=None`) and no-kwarg paths
  never enter the semantic code. The new module-level `from flowstate.embeddings import
  get_embedder` import is side-effect-free (importing `flowstate.embeddings` never imports
  fastembed; no eager corpus glob or embed at import time). The pre-existing
  `TestWikiLayer` (10) and `TestDeterminism` golden tests pass UNMODIFIED — confirmed by
  running them. Default-path output is provably untouched.
- **No FTS5/hybrid gate (Phase 10 recurrence — clear):** `_semantic_wiki_layer` is pure
  semantic KNN (`vec0` + `serialize_float32` + `ORDER BY distance LIMIT ?`) with no lexical
  or FTS5 precondition. The omitted distance floor is correct for this layer: a real run
  query always wants its k most-relevant articles, and there is no garbage-query golden
  test for wiki. (See IN-01 for the one operational caveat.)
- **Ephemeral vec conn lifecycle (Phase 9 CR-01 recurrence — clear):**
  `enable_load_extension(False)` is re-scoped immediately after `sqlite_vec.load(conn)`
  inside the try; `conn.close()` is in `finally`, so the `:memory:` connection is always
  closed and never leaks, even if `enable_load_extension(True)`, `load`, or the DDL raises.
- **never-raises (verified):** Every degraded path (no corpus dir, blank query, embedder
  None/unavailable, empty vectors, `sqlite_vec` ImportError, empty KNN) returns `None`, and
  the whole body is wrapped in `try/except Exception: return None`. The
  `test_semantic_path_never_raises_on_embed_error` test confirms an embed-time exception
  falls back to the static read and returns a `str`.
- **CANON exclusion (verified):** No `flowstate.bridge` import — only the docstring
  references it. `grep` confirms.
- **`_load_wiki_k` (verified):** env > config > default(3) precedence; rejects bool, zero,
  negative, and non-int at each tier via `isinstance(value, int) and not
  isinstance(value, bool) and value > 0`. The dedicated test exercises all branches.

Full suite: 749 passed, 92.19% coverage, ruff clean. The single Warning is dead code
ported verbatim from the bench reference; the Info items are minor test-robustness and
observability notes. None block shipping the mechanism.

## Warnings

### WR-01: Dead `paths` list — carried from the bench port but never read

**File:** `flowstate/context_prefix.py:249,256`
**Issue:** `_semantic_wiki_layer` builds `paths: list[str]` and `paths.append(str(p))`
alongside `contents`, mirroring bench `_retrieve_vec`. But unlike the bench function — which
returns `(paths[r[0]], contents[r[0]])` tuples — this helper maps results with
`contents[r[0]]` only (line 303) and discards paths entirely. The list is pure dead code:
allocated and populated every call, never consumed. Ruff does not flag it because `.append`
counts as a use, so it slipped through the lint gate. This is the kind of port-residue that
quietly drifts: a future reader may assume `paths` participates in the result and index it,
introducing a real bug.
**Fix:** Drop the `paths` list and its append. The loop only needs `contents`:
```python
        contents: list[str] = []
        for p in sorted(corpus_dir.glob("**/*.md")):
            try:
                text = p.read_text(errors="ignore")
                if not text.strip():
                    continue
                contents.append(text)
            except Exception:
                continue
```

## Info

### IN-01: No distance floor means an off-topic run will still inject k wiki articles

**File:** `flowstate/context_prefix.py:235-238,292-304`
**Issue:** The intentional omission of a relevance/distance threshold is correct for the
stated rationale, but it has one operational consequence worth recording: when the wiki
layer is active, EVERY run injects its k nearest articles regardless of how far they are —
even a run whose query is unrelated to anything in the corpus gets k (default 3) articles
prepended. Today this is inert (the only production caller, `orchestrator.py:254`, passes no
`include_layers`, so the wiki layer never fires in production — the corpus/curation is
WIKI-F1, deferred). It becomes live the moment a caller opts in. Not a bug; a documented
design tradeoff with no observability.
**Fix:** No code change required for this milestone. When the wiki layer is wired into a
production caller, consider logging the selected article paths + distances via the existing
`con.print` seam (as the pack layer already logs its decisions) so an irrelevant injection
is diagnosable rather than silent.

### IN-02: Fallback test uses a weakened `or` assertion that can mask a real mismatch

**File:** `tests/test_context_prefix.py` (`test_embedder_absent_falls_back_to_static_read`,
the final assert)
**Issue:** The test extracts `wiki_slice = result[wiki_start:]` and asserts
`wiki_slice == expected or expected in result`. The first (strict) disjunct only holds when
wiki is the last layer; otherwise the trailing `_SEPARATOR` + following layers make the
`==` fail and the test silently falls back to the weaker `expected in result` substring
check. The substring disjunct would pass even if the fallback emitted the static content in
a subtly wrong position or with altered surrounding bytes. The byte-identity intent of the
embedder-absent path is therefore only loosely enforced.
**Fix:** Assert against the wiki layer in isolation — split `result` on `_SEPARATOR` and
assert one segment `== expected`, or arrange the test so wiki is the only/last layer and
drop the `or` disjunct:
```python
    segments = result.split("\n\n---\n\n")
    assert expected in segments, "embedder-absent wiki segment must equal _read_wiki_layer output"
```

### IN-03: Byte-identity test proves self-consistency, not parity with pre-Phase-11 output

**File:** `tests/test_context_prefix.py`
(`test_default_path_byte_identical_with_corpus_present`)
**Issue:** The test asserts `result_default == result_none` — i.e. no-kwarg equals
`include_layers=None`. Both invocations take the identical default code path, so this
equality is near-tautological and would hold even if Phase 11 had regressed the default
output, as long as it regressed both calls identically. The genuine WIKI-02 guarantee
(parity with pre-Phase-11 bytes) is actually carried by the unmodified `TestWikiLayer` /
`TestDeterminism` golden tests, which do pass. The added test's real value is the second
assertion (`## Codebase Wiki` absent even with a corpus dir present), which IS a meaningful
regression guard.
**Fix:** No change strictly required (the golden tests cover the parity contract). If
hardening is wanted, assert the default output against a stored golden string or against the
pre-Phase-11 `_read_*` composition, rather than against itself.

---

_Reviewed: 2026-06-18_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
