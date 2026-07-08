---
id: 260708-mjt
status: complete
phase: quick
plan: 260708-mjt
subsystem: bench
tags: [tdd, benchmark, retrieval, longmemeval, locomo, bm25, semantic]
created: 2026-07-08
completed: 2026-07-08
commits:
  red: b1d962c
  green: fcb87ef
---

# Quick Task 260708-mjt: LongMemEval + LoCoMo Retrieval Benchmark Harnesses

## One-liner

ADD-ONLY TDD implementation of two retrieval benchmark harnesses (LongMemEval Recall@k, LoCoMo evidence-coverage) with shared BM25/FTS5 + sqlite-vec backends, 31 offline tests, and synthetic fixtures.

## What Was Built

Five new files created; zero existing files modified:

| File | Purpose |
|------|---------|
| `bench/_retrieval.py` | Shared BM25/FTS5 and sqlite-vec KNN backends (never-raises, optional semantic) |
| `bench/longmemeval.py` | Session-level `recall_any@k` + `recall_all@k` with Wilson CI; k in {5,10} |
| `bench/locomo.py` | Evidence `coverage` + `full_coverage_rate` with Wilson CI; configurable top-n |
| `bench/fixtures/lme_smoke.json` | 3 synthetic LongMemEval instances (single-gold, multi-gold, abstention) |
| `bench/fixtures/locomo_smoke.json` | 1 synthetic LoCoMo conversation (6 sessions, 4 QA items incl. abstention) |

Two test modules (committed in RED gate):

| File | Tests |
|------|-------|
| `tests/test_longmemeval.py` | 15 tests: loader, metric-math, BM25, semantic (skip w/o sqlite_vec), main() |
| `tests/test_locomo.py` | 16 tests: loader, metric-math, BM25, semantic (skip w/o sqlite_vec), main() |

## TDD Gate Compliance

- **RED commit:** `b1d962c` — `test(260708-mjt): add failing tests for LongMemEval and LoCoMo retrieval harnesses`
- **GREEN commit:** `fcb87ef` — `feat(260708-mjt): implement LongMemEval and LoCoMo retrieval harnesses (GREEN)`
- RED gate: both test files raised `ModuleNotFoundError` on collection (no implementation existed)
- GREEN gate: 31/31 tests pass after implementation

## Verification Gates Passed

- 31/31 new tests: `uv run python -m pytest tests/test_longmemeval.py tests/test_locomo.py -v --no-cov`
- Full suite: 829 tests passed, 92% coverage (>80% threshold)
- Ruff: `ruff check` + `ruff format --check` clean on all 3 new bench files
- LME smoke: `python -m bench.longmemeval --data bench/fixtures/lme_smoke.json --backends bm25 --k 5,10` → BM25 recall_all/recall_any both 1.000 on 2 evaluated instances
- LoCoMo smoke: `python -m bench.locomo --data bench/fixtures/locomo_smoke.json --backends bm25 --top-n 5` → mean_coverage 1.000, full_coverage_rate 1.000 on 3 QA items
- ADD-ONLY proof: `git diff --quiet bench/grounding.py flowstate/` → exit 0

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FTS5 AND semantics fail on short conversation turns**
- **Found during:** Task 2 (GREEN), running `test_bm25_backend_on_locomo_smoke_single_evidence`
- **Issue:** `_sanitize_fts_query` from `bench.grounding` produces AND semantics (space-separated quoted tokens all required). Short conversation turns (1-3 sentences) don't contain every query token, so BM25 returned `[]` for LoCoMo QA queries.
- **Fix:** Added `_fts5_or_query()` to `bench/_retrieval.py` that joins tokens with `OR`; `bm25_rank` uses OR semantics. `_sanitize_fts_query` still imported from `bench.grounding` (re-exported for AND-style callers on long documents, per the plan's key_link requirement).
- **Files modified:** `bench/_retrieval.py`

**2. [Rule 1 - Bug] Monkeypatch ineffective with `from X import Y` binding**
- **Found during:** Task 2 (GREEN), running `test_semantic_unavailable_bm25_still_runs`
- **Issue:** Both harnesses imported `from bench._retrieval import semantic_backend_available`. Monkeypatching `bench._retrieval.semantic_backend_available` had no effect on the already-bound reference inside each harness module.
- **Fix:** Changed both harnesses to `import bench._retrieval as _retrieval` and called all shared functions via `_retrieval.xxx()`. This allows pytest monkeypatch to replace the attribute on the module object, which the harnesses now dereference at call time.
- **Files modified:** `bench/longmemeval.py`, `bench/locomo.py`

## Metric Fidelity

| Metric | Formula | Implementation |
|--------|---------|----------------|
| `recall_any@k` | `1.0 if any(g in ranked[:k] for g in gold)` | `_recall_any` in longmemeval.py |
| `recall_all@k` | `1.0 if all(g in ranked[:k] for g in gold)` | `_recall_all` in longmemeval.py |
| `coverage` | `|gold ∩ retrieved| / |gold|` | `_coverage` in locomo.py |
| `full_coverage` | `1 if gold ⊆ retrieved else 0` | `_full_coverage` in locomo.py |
| Wilson CI | 95% normal-approx (via `_wilson` from bench.grounding) | `_aggregate` in both harnesses |

## Known Stubs

None — both harnesses are fully wired; BM25 runs against real in-memory FTS5; semantic arm degrades gracefully with a printed note when fastembed/sqlite_vec are absent.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. All I/O is local file reads + in-memory SQLite.
