---
phase: quick-260525-m9v
plan: 01
status: complete
subsystem: orchestrator
tags: [memory, prompt-cache, refactor, cag]
dependency_graph:
  requires:
    - flowstate.memory.MemoryStore.get_context (preserved as escape hatch)
    - flowstate.tools.ToolAdapter (extended signature)
  provides:
    - ToolAdapter.prior_knowledge attribute (str | None)
    - Unified orchestrator-level prior_knowledge build + thread pattern
  affects:
    - flowstate.tools.research.ResearchAdapter
    - flowstate.tools.strategy.StrategyAdapter
    - flowstate.orchestrator.run_pipeline
tech_stack:
  added: []
  patterns:
    - Build-once-thread-many for shared LLM context (CAG-aligned)
    - Constructor-injected prior knowledge over per-call memory lookups
key_files:
  created: []
  modified:
    - flowstate/tools/base.py
    - flowstate/tools/research.py
    - flowstate/tools/strategy.py
    - flowstate/orchestrator.py
    - tests/test_tools.py
    - tests/test_tools_extended.py
    - tests/test_orchestrator.py
decisions:
  - "Default prior_knowledge=None (not '') — distinguishes 'not provided' from 'provided but empty'"
  - "Build prior_knowledge block AFTER interview memory.add() — interview row participates in retrieval"
  - "Thread prior_knowledge into GSDAdapter even though it does not consume it — uniform contract, future-proof"
  - "MemoryStore.get_context() preserved as escape hatch per user plan (consider-how-and-if-witty-grove.md)"
  - "Query for unified block: core_problem + ten_x_vision + research_focus joined — broad enough to cover all tools"
metrics:
  duration: "4m 39s"
  completed: "2026-05-25T20:10:46Z"
  tests_added: 7
  total_tests: 297
  coverage: "91.41%"
  commits: 3
requirements:
  - QUICK-M9V-01
---

# Quick-260525-m9v: Unify Memory Injection at Orchestrator Level — Summary

**One-liner:** Build the `prior_knowledge` block ONCE at orchestrator pipeline start (after interview seeding) and thread it via constructor kwarg into Research, Strategy, and GSD adapters — eliminating N+1 redundant FTS5 searches and enabling Anthropic's server-side prompt cache to hit across pipeline steps.

## Objective

Today each tool independently calls `self.get_memory_context(query)` with a query-specific string, producing slightly different prefixes per call and defeating Anthropic's server-side prompt cache (5-min TTL). This plan consolidates memory injection at the orchestrator level so the same prefix is reused across Research → Strategy → GSD calls. Aligned with arXiv 2412.15605v1 (Cache-Augmented Generation) without adopting the full CAG pattern.

## Changes

### `flowstate/tools/base.py`
- Extended `ToolAdapter.__init__` with `prior_knowledge: str | None = None` kwarg, stored on `self.prior_knowledge`.
- `get_memory_context()` method **preserved unchanged** as escape hatch for callers needing a query-specific slice.

### `flowstate/tools/research.py`
- `ResearchAdapter.execute()` now reads `self.prior_knowledge or ""` ONCE before the per-topic loop (was: `self.get_memory_context(topic)` per topic).
- Same `\n\n---\n\n` separator preserved → prompt shape unchanged when injection is present.

### `flowstate/tools/strategy.py`
- `StrategyAdapter.pressure_test()` now reads `self.prior_knowledge or ""` instead of calling `self.get_memory_context(...)`.

### `flowstate/orchestrator.py`
- After `memory.add(...)` for interview answers and BEFORE adapter construction, the orchestrator now:
  1. Builds `_pk_query` from `core_problem + ten_x_vision + research_focus` (space-joined, empty-strings filtered).
  2. Calls `memory.get_context(_pk_query)` exactly once if the query is non-empty; otherwise `prior_knowledge = ""`.
  3. Threads `prior_knowledge=prior_knowledge` into all three adapter constructors (Research, Strategy, GSD).

### Tests added (7 total — plan called for 6, +1 for empty-interview coverage)

**`tests/test_tools_extended.py` (+2):**
- `test_prior_knowledge_accepted_and_stored` — base accepts/stores the kwarg
- `test_prior_knowledge_default_none_when_omitted` — default is `None`

**`tests/test_tools.py` (+4):**
- `test_research_prepends_injected_prior_knowledge` — every per-topic prompt starts with injected block + `\n\n---\n\n`
- `test_research_no_prior_knowledge_no_prefix` — no `## Prior Knowledge` substring when none provided
- `test_strategy_prepends_injected_prior_knowledge` — same shape for pressure-test prompt
- `test_research_does_not_call_get_memory_context_when_prior_knowledge_set` — spy on `MemoryStore.get_context` confirms zero per-tool lookups

**`tests/test_orchestrator.py` (+2):**
- `test_pipeline_builds_prior_knowledge_once_and_threads_it` — end-to-end: spy confirms exactly 1 `get_context` call; all three adapters receive the SAME `prior_knowledge` kwarg value
- `test_pipeline_empty_interview_skips_memory_lookup` — branch coverage for `if _pk_query else ""` (zero calls when interview is blank)

## Deviations from Plan

**1. [Rule 2 — Missing branch coverage] Added empty-interview test**
- **Found during:** Coverage analysis after Task 2 integration test
- **Issue:** The plan's Task 2 noted: *"If coverage drops below 80%, identify the uncovered lines (likely the new orchestrator branch when `_pk_query` is empty) and add a small dry-run test with empty interview to cover it."* Plan called for 6 tests; added a 7th preventively to cover the empty-query branch.
- **Fix:** Added `test_pipeline_empty_interview_skips_memory_lookup` in same commit as integration test.
- **Files modified:** `tests/test_orchestrator.py`
- **Commit:** `1e79097`

No other deviations. Plan executed as written.

## Verification

```
uv run pytest tests/ --cov=flowstate --cov-fail-under=80 -q
297 passed, 1 warning in 40.81s
Required test coverage of 80% reached. Total coverage: 91.41%
```

Contract grep confirms the wiring:
- `flowstate/orchestrator.py:238` — exactly one `memory.get_context(_pk_query)` call
- `flowstate/orchestrator.py:246, 267, 290` — three `prior_knowledge=prior_knowledge` adapter kwargs
- `flowstate/tools/base.py:60` — `get_memory_context()` method still present (escape hatch)
- `flowstate/tools/research.py` and `strategy.py` — only `self.prior_knowledge` reads, no `self.get_memory_context(` calls

No changes to `pyproject.toml`; no new runtime dependencies.

## Commits

1. `d4f9644` — `test(quick-m9v): add failing tests for unified prior_knowledge injection` (RED)
2. `fe35fa4` — `feat(quick-m9v): unify memory injection at orchestrator level` (GREEN)
3. `1e79097` — `test(quick-m9v): integration test for unified prior_knowledge threading` (orchestrator-level proof)

## Self-Check: PASSED

- `flowstate/tools/base.py` — FOUND (prior_knowledge in __init__, get_memory_context preserved)
- `flowstate/tools/research.py` — FOUND (self.prior_knowledge read, no get_memory_context call)
- `flowstate/tools/strategy.py` — FOUND (self.prior_knowledge read, no get_memory_context call)
- `flowstate/orchestrator.py` — FOUND (single memory.get_context, three adapter kwargs)
- `tests/test_tools_extended.py` — FOUND (2 new tests)
- `tests/test_tools.py` — FOUND (4 new tests)
- `tests/test_orchestrator.py` — FOUND (2 new tests)
- Commit `d4f9644` — FOUND
- Commit `fe35fa4` — FOUND
- Commit `1e79097` — FOUND
- Full suite 297 passed at 91.41% coverage — VERIFIED
