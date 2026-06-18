---
phase: 11-semantic-wiki-retrieval
plan: "01"
status: complete
subsystem: context-prefix
tags: [sqlite-vec, semantic-retrieval, embeddings, wiki, knn, context-prefix]

requires:
  - phase: 09-embeddings-foundation
    provides: get_embedder(root, embed_fn=) + Embedder.available/embed/dim seam

provides:
  - _semantic_wiki_layer: ephemeral :memory: vec0 KNN over wiki corpus articles
  - _load_wiki_k: env > config.json > default(3) precedence helper
  - _WIKI_CORPUS_DIR constant (.planning/codebase/wiki/)
  - Semantic top-k injection wired into the opt-in wiki branch of build_context_prefix
  - TestWikiSemantic: 5 offline tests (top-k, byte-identity, fallback, never-raises, k precedence)

affects:
  - context-prefix consumers (orchestrator, adapters that pass include_layers=frozenset({"wiki"}))
  - bench/grounding.py wiki arm (unaffected — bench uses its own _retrieve_vec directly)

tech-stack:
  added: []
  patterns:
    - "Ephemeral :memory: vec0 conn for single-use KNN; always closed in finally; extension re-scoped OFF immediately after load (T-11-01/CR-01)"
    - "Opt-in layer stays outside _included() helper — never activated on default path"
    - "Semantic-first with static fallback: try _semantic_wiki_layer → None triggers _read_wiki_layer"
    - "Offline test injection: monkeypatch flowstate.context_prefix.get_embedder; skipif _HAS_VEC"

key-files:
  created: []
  modified:
    - flowstate/context_prefix.py
    - tests/test_context_prefix.py

key-decisions:
  - "No distance/relevance floor for wiki layer: unlike memory.get_context there is no 'must return empty for garbage query' golden test; a real run always wants its k most-relevant articles, so the L2 floor from Phase 10 is intentionally omitted for simplicity"
  - "enable_load_extension(False) re-scope applied immediately after sqlite_vec.load on the ephemeral :memory: conn (T-11-01 mitigation, mirror of Phase 9 CR-01)"
  - "_WIKI_CORPUS_DIR distinct from _WIKI_PATH: corpus dir is the article directory for semantic retrieval; single-file wiki.md remains the static fallback source"
  - "wiki_included gate unchanged: uses include_layers is not None and 'wiki' in include_layers — never routed through _included() to preserve byte-identical default path"

patterns-established:
  - "Never-raises semantic layer: wrap entire body in try/except Exception: return None; caller decides fallback"
  - "Semantic path returns None on any degraded condition (missing corpus dir, unavailable embedder, empty results, import error) — None signals caller to fall back, not raise"

requirements-completed: [WIKI-01, WIKI-02]

duration: 25min
completed: 2026-06-18
---

# Phase 11 Plan 01: Semantic Wiki Retrieval Summary

**Ephemeral sqlite-vec KNN over a wiki article corpus injected into the opt-in wiki layer of build_context_prefix, with byte-identical default path and never-raises static fallback**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-18T19:54:00Z
- **Completed:** 2026-06-18T20:19:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Ported bench `_retrieve_vec` KNN mechanics into `_semantic_wiki_layer` inside `context_prefix.py`: ephemeral `:memory:` vec0 table, `enable_load_extension(False)` re-scope (T-11-01/CR-01), `serialize_float32` parameterized inserts (T-11-02), never raises
- Wired semantic helper into the existing `wiki_included` branch: semantic-first → None signals fallback to `_read_wiki_layer`; default path (include_layers=None) byte-identical
- Added `_load_wiki_k` with env (`FLOWSTATE_WIKI_K`) > `config.json` > default(3) precedence; booleans and non-positive values rejected at each tier
- Added 5 offline tests in `TestWikiSemantic`: top-k selection (relevant present + irrelevant absent), byte-identity default with corpus present, embedder-absent static fallback, never-raises on embed error, `_load_wiki_k` precedence + bad-value rejection

## Task Commits

1. **Task 1: Semantic wiki retrieval helper + wire into opt-in wiki branch** - `86545cb` (feat)
2. **Task 2: Offline semantic-wiki tests** - `9fea5ba` (test)

## Files Created/Modified

- `/Users/jhogan/frameworx/flowstate/context_prefix.py` - Added `_WIKI_CORPUS_DIR`, `_DEFAULT_WIKI_K`, `_WIKI_K_ENV_VAR` constants; `_load_wiki_k`; `_semantic_wiki_layer`; `get_embedder` import; wired into `wiki_included` branch
- `/Users/jhogan/frameworx/tests/test_context_prefix.py` - Added `_HAS_VEC` guard, `_fake_embed_factory`, `_make_wiki_corpus`, `TestWikiSemantic` (5 tests)

## Decisions Made

- No L2/cosine distance floor on the wiki layer (unlike Phase 10 memory seam). A real run query always wants its k most-relevant articles; the floor exists in memory to handle garbage queries that should return empty, but there is no equivalent golden test for wiki.
- `enable_load_extension(False)` applied immediately after `sqlite_vec.load` on the throwaway `:memory:` conn — T-11-01 mitigation, consistent with Phase 9 CR-01.
- `_WIKI_CORPUS_DIR` is the article directory for semantic retrieval; `_WIKI_PATH` (single file) is the fallback source. Both exist independently.
- `import sqlite_vec` is a local import inside the try block — ImportError returns None (fallback), not a raise.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff reformatted `_WIKI_CORPUS_DIR` constant to a multi-line form (long inline comment). First commit failed pre-commit hook due to ruff-format; re-staged the formatted file and committed successfully.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The implementation reads only operator-owned files under `root / .planning/codebase/wiki/` — consistent with T-11-03 (accepted, operator-scoped). Extension loader re-scoped OFF per T-11-01. SQL values bound as parameters per T-11-02.

## Known Stubs

None.

## Self-Check

Files exist:
- `/Users/jhogan/frameworx/flowstate/context_prefix.py` - FOUND
- `/Users/jhogan/frameworx/tests/test_context_prefix.py` - FOUND

Commits exist: 86545cb (feat), 9fea5ba (test) - FOUND

Suite: 749 passed, 92.19% coverage — PASSED

## Self-Check: PASSED

---
*Phase: 11-semantic-wiki-retrieval*
*Completed: 2026-06-18*
