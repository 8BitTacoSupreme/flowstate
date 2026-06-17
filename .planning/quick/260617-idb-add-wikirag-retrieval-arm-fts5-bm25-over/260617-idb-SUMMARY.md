---
phase: quick-260617-idb
plan: "01"
status: complete
subsystem: bench
tags: [wikirag, fts5, bm25, retrieval, grounding]
dependency_graph:
  requires: [260617-dv6]
  provides: [wikirag-arm]
  affects: [bench/grounding.py, tests/test_bench_grounding.py]
tech_stack:
  added: [sqlite3 in-memory FTS5 virtual table]
  patterns: [porter unicode61 tokenizer, BM25 rank via ORDER BY rank]
key_files:
  modified:
    - bench/grounding.py
    - tests/test_bench_grounding.py
decisions:
  - "_sanitize_fts_query strips embedded double-quotes per token (not just wrapping) to prevent FTS5 string escaping from bare quotes in query input"
  - "wikirag guard placed at arm-loop level with continue — cleanest integration with existing trial/arm/probe nesting"
  - "zero-records guard (all arms empty) placed before aggregation so no division-by-zero can occur and non-zero rc is returned when only arm was skipped"
  - "budget_chars = budget_tokens * 4 matches the 4 chars-per-token heuristic used elsewhere in the codebase"
metrics:
  duration: "~8m"
  completed: "2026-06-17"
  tasks_completed: 2
  files_modified: 2
  commits: 2
  tests_added: 7
  total_tests: 689
  coverage: "92%"
---

# Phase quick-260617-idb Plan 01: WikiRAG Retrieval Arm Summary

**One-liner:** Per-probe FTS5/BM25 retrieval arm (`wikirag`) over a wiki directory with porter-unicode61 tokenizer, never-raises guard, and `retrieved` path list in per-probe records.

## What Was Built

Extended `bench/grounding.py` with a new `wikirag` arm that runs real BM25 retrieval (sqlite3 in-memory FTS5) per probe instead of using `build_context_prefix` or `MemoryStore`. Enables measuring "grounding from hand-placed article" vs "grounding from retrieved article" as a causal comparison.

### bench/grounding.py additions (ADD-ONLY)

- `import sqlite3` (alphabetical, after `re`)
- `_sanitize_fts_query(query)`: mirrors `flowstate/memory.py:_sanitize_fts_query`; wraps each whitespace-split token in double-quotes, strips embedded quotes to prevent FTS5 parse errors
- `_retrieve_wiki(wiki_dir, query, k)`: in-memory FTS5 virtual table (`porter unicode61`); globes `**/*.md`; `ORDER BY rank LIMIT k`; never raises
- `_build_parser`: adds `"wikirag"` to `--layers` choices, `--wiki-dir` (Path), `--rag-k` (int, default 3)
- `main()`: `budget_chars = budget_tokens * 4`; wikirag arm branch skips `MemoryStore`/`build_context_prefix`, calls `_retrieve_wiki`, populates `retrieved`; all arm records now include `"retrieved"` key; zero-records guard returns 1

### tests/test_bench_grounding.py additions (ADD-ONLY, 7 new tests)

All new tests use real temp directories and real sqlite3 FTS5 (stdlib); LLM calls mocked via monkeypatch.

| Test | What it verifies |
|------|-----------------|
| `test_retrieve_wiki_ranks_match_first` | BM25 ranks unique-term doc first in 3-doc corpus |
| `test_retrieve_wiki_respects_k` | k=2 caps results over 5-doc corpus |
| `test_retrieve_wiki_missing_and_empty_dir` | missing path and empty dir both return `[]` |
| `test_retrieve_wiki_nonsense_query_never_raises` | special-char and empty query return list, no exception |
| `test_sanitize_fts_query_handles_special_chars` | sanitized string executes against real FTS5, no OperationalError |
| `test_wikirag_arm_records_retrieved_and_skips_bcp` | `retrieved` paths in per_probe; `build_context_prefix` NOT called |
| `test_wikirag_no_dir_clear_message_no_subprocess` | rc!=0; zero subprocess.run calls; "wiki-dir" in stdout |

## Commits

| Hash | Message |
|------|---------|
| `8165b8b` | feat(quick-260617-idb): add _sanitize_fts_query, _retrieve_wiki, wikirag arm to grounding.py |
| `5b53065` | test(quick-260617-idb): wikirag retrieval + sanitizer + arm integration tests |

## Verification

- `git diff --name-only 0d8d297..HEAD` → `bench/grounding.py`, `tests/test_bench_grounding.py` only
- `pytest tests/ --cov=flowstate --cov-fail-under=80` → 689 passed, 92.42% coverage
- `ruff check flowstate/ bench/ tests/` → clean
- `ruff format --check flowstate/ bench/ tests/` → clean

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `bench/grounding.py` exists and contains `def _retrieve_wiki`, `def _sanitize_fts_query`, `wikirag`, `docs MATCH ? ORDER BY rank`, `tokenize=`
- `tests/test_bench_grounding.py` exists and contains `def test_retrieve_wiki`
- Commits `8165b8b` and `5b53065` verified in git log
