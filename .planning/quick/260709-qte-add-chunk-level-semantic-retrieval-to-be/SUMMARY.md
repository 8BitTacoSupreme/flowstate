---
phase: quick-260709-qte
plan: "01"
status: complete
subsystem: bench
tags: [semantic-retrieval, chunking, sqlite-vec, max-sim-rollup, tdd]
dependency_graph:
  requires: [bench._retrieval, bench.longmemeval]
  provides: [bench._retrieval.semantic_rank_chunked, bench.longmemeval --chunk-tokens]
  affects: []
tech_stack:
  added: []
  patterns: [module-attribute-imports, max-sim-rollup, never-raises, chunk-then-embed-batch]
key_files:
  created:
    - tests/test_retrieval_chunked.py
  modified:
    - bench/_retrieval.py
    - bench/longmemeval.py
    - tests/test_longmemeval.py
decisions:
  - "chunk_chars = chunk_tokens * 4 (rough token-to-char heuristic, consistent with bge tokenizer assumptions elsewhere in the codebase)"
  - "Max-sim rollup over-fetches KNN with LIMIT = total chunk count, then takes the MIN distance per doc_id in Python — simpler and more predictable than a SQL GROUP BY on a vec0 virtual table"
  - "--chunk-tokens default 0 preserves byte-identical output to the pre-existing semantic_rank path so prior benchmark numbers remain reproducible"
metrics:
  duration: ~15 min
  completed: "2026-07-09"
  tasks_completed: 2
  files_changed: 4
---

# Quick Task 260709-qte: Chunk-level semantic retrieval for LongMemEval

Added `semantic_rank_chunked` (max-sim rollup over sqlite-vec KNN across whitespace-packed chunks) to recover semantic matches buried past a real embedder's head-truncation window, wired behind a new `--chunk-tokens` flag in `bench/longmemeval.py` that defaults to the existing byte-identical `semantic_rank` path.

## What Was Built

`bench/_retrieval.py` (ADD-ONLY — existing `semantic_rank` untouched):
- `_chunk_text(text, chunk_tokens)` — splits text into whitespace-boundary windows of ~`chunk_tokens*4` chars, packing words greedily without ever cutting a word mid-token; blank/empty text -> `[]`; short text -> single-element list.
- `semantic_rank_chunked(docs, query, k, embed_fn, *, chunk_tokens=400)` — chunks every doc, batch-embeds all chunks in one `embed_fn` call, runs vec0 KNN over the full chunk set (LIMIT = chunk count), then rolls each doc's score up to its BEST (min-distance) chunk, dedupes, and returns the top-k doc ids. Never raises — any exception (missing `sqlite_vec`, embed failure, etc.) is caught, printed, and `[]` is returned.

`bench/longmemeval.py`:
- New `--chunk-tokens` argparse flag (default `0`). `0` keeps the existing `_retrieval.semantic_rank(...)` ranker call unchanged (reproducible); `>0` routes to `_retrieval.semantic_rank_chunked(..., chunk_tokens=N)`. Both branches use module-attribute access on `_retrieval` so tests can monkeypatch either function independently.
- `chunk_tokens` is recorded in the output JSON alongside `embed_model`.

`tests/test_retrieval_chunked.py` (new, 10 tests):
- `_chunk_text`: long-doc splitting + no-word-cut round-trip, short-doc single-chunk, blank-text empty-list.
- `test_max_sim_rollup` (the core proof): a gold doc's match term lands in its SECOND chunk (first chunk is exact-fill filler). A fake `embed_fn` simulates a real embedder's fixed-token-window truncation via a `head_chars` probe cap. `semantic_rank_chunked` ranks the gold doc first; plain `semantic_rank` — which only ever sees the truncated whole-doc head — does NOT rank it first (a distractor with a head-visible marker wins instead).
- `test_dedup`: a doc whose every chunk matches appears exactly once in results.
- `test_k_semantics`: 3 matching docs, k=2 -> exactly 2 results.
- `test_never_raises_embed_error` (skipif no sqlite_vec): raising `embed_fn` -> `[]`.
- `test_never_raises_no_vec` (no skipif, `sys.modules["sqlite_vec"] = None` via monkeypatch): missing backend -> `[]`.
- `test_blank_query_or_empty_docs_returns_empty`: early-return path never touches `embed_fn`.

`tests/test_longmemeval.py` (2 new tests added, existing tests unchanged):
- `test_chunk_tokens_zero_uses_plain_semantic`: `--chunk-tokens` omitted (default 0) -> `semantic_rank` called, `semantic_rank_chunked` NOT called; JSON `chunk_tokens == 0`.
- `test_chunk_tokens_positive_uses_chunked`: `--chunk-tokens 400` -> `semantic_rank_chunked` called, `semantic_rank` NOT called; JSON `chunk_tokens == 400`.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `7a67cec` | test (RED) | Failing tests for semantic_rank_chunked + --chunk-tokens |
| `585ae5e` | feat (GREEN) | Implement semantic_rank_chunked + --chunk-tokens wiring |

## Verification

- `python -m pytest tests/test_retrieval_chunked.py tests/test_longmemeval.py -q` -> 25 passed
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80` -> 938 passed, 92.07% coverage
- `ruff check bench/_retrieval.py bench/longmemeval.py tests/test_retrieval_chunked.py tests/test_longmemeval.py` -> clean
- `ruff format --check bench/_retrieval.py bench/longmemeval.py` -> clean
- `git diff --name-only` (across both commits) -> only `bench/_retrieval.py`, `bench/longmemeval.py`, `tests/test_retrieval_chunked.py`, `tests/test_longmemeval.py`; grep confirms `bench/grounding.py`, `bench/locomo*.py`, `bench/longmemeval_qa.py`, `flowstate/`, `pyproject.toml` untouched.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `bench/_retrieval.py` — modified and committed at `585ae5e`
- `bench/longmemeval.py` — modified and committed at `585ae5e`
- `tests/test_retrieval_chunked.py` — created and committed at `7a67cec`
- `tests/test_longmemeval.py` — modified and committed at `7a67cec`
- 25 targeted tests pass; full suite (938 tests) green at 92.07% coverage; ruff clean; diff scoped to exactly the 4 allowed files
