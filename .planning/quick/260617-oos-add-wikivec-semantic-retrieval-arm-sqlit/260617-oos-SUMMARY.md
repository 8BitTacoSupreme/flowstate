---
phase: quick-260617-oos
plan: 01
status: complete
subsystem: bench
tags: [grounding, retrieval, wikivec, sqlite-vec, fastembed, bench]
decisions:
  - Lazy fastembed import inside _default_embedder (not module top-level) so bench.grounding imports without fastembed
  - Single atomic embed_fn built once before trial loop (not per-probe) for performance
  - noqa PLC0415 removed (not enabled in ruff config); plain inline comments used instead
  - Two commits: source (feat) then tests (test), matching plan output spec
metrics:
  duration: ~10 minutes
  completed: "2026-06-17"
  tests_added: 8
  tests_total: 697
  coverage: 92.42%
---

# Phase quick-260617-oos Plan 01: Add wikivec Semantic Retrieval Arm Summary

**One-liner:** Added sqlite-vec KNN semantic retrieval arm (`wikivec`) to grounding harness via lazy fastembed import (`_default_embedder`) and `_retrieve_vec` mirroring the existing `wikirag` BM25 arm's never-raises contract.

## What Was Built

- `_default_embedder(model_name)` — lazy `from fastembed import TextEmbedding` inside the function; raises `RuntimeError` with install hint on failure; returns `embed_fn(texts) -> list[list[float]]` closure.
- `_retrieve_vec(wiki_dir, query, k, embed_fn)` — sqlite-vec KNN over fastembed embeddings; in-memory `vec0` virtual table; never raises; returns `[]` on missing dir, blank query, or any exception.
- `wikivec` arm dispatch in `main()`: guard before probe loop (skips if no `--wiki-dir` or `embed_fn is None`), `elif arm == "wikivec"` branch using `_retrieve_vec`; does NOT call `build_context_prefix`.
- `--embed-model` CLI arg (default `BAAI/bge-small-en-v1.5`); `"wikivec"` added to `--layers` choices.
- `embed_model` field added to output JSON.

## Key Files

- **Modified:** `/Users/jhogan/frameworx/bench/grounding.py` — +103 lines, -2 lines (docstring expansion)
- **Modified:** `/Users/jhogan/frameworx/tests/test_bench_grounding.py` — +224 lines

## Commits

- `5ebf535` — `feat(260617-oos): add _default_embedder + _retrieve_vec + wikivec arm to grounding harness`
- `eb28d5d` — `test(260617-oos): add wikivec arm tests with injected fake embed_fn (no fastembed/network)`

## Test Results

- **697 passed** (689 existing + 8 new), 0 failed
- **Coverage:** 92.42% (gate: 80%)
- **Ruff:** clean (check + format --check)
- **Changed files:** `bench/grounding.py`, `tests/test_bench_grounding.py` only

## Deviations from Plan

None — plan executed exactly as written. The `noqa: PLC0415` directive was dropped (ruff flagged it as non-enabled; plain inline comments used instead — functionally identical).

## Known Stubs

None. No UI surface. No placeholder data.
