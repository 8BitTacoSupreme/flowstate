---
phase: 07-gotchas-accumulator
plan: "02"
subsystem: context_prefix
status: complete
tags: [gotchas, context-prefix, budget-guard, layer-ordering, GOT-02, GOT-03]
dependency_graph:
  requires: [07-01]
  provides: [gotchas-prefix-layer, gotchas-budget-participation]
  affects: [flowstate/context_prefix.py, tests/test_context_prefix.py]
tech_stack:
  added: []
  patterns:
    - _load_*_budget idiom extended to three new config keys
    - two-pass stable sort (last_seen desc then count desc) for ranking
    - greedy token-budget trim (pop trailing blocks until fits)
    - CR-01 budget-participation pattern applied to gotchas layer
key_files:
  created: []
  modified:
    - flowstate/context_prefix.py
    - tests/test_context_prefix.py
decisions:
  - Two-pass stable sort for ranking (last_seen desc then count desc) preferred over
    tuple-key because Python stable sort guarantees secondary-sort preservation
  - assert_any_call replaces assert_called_once_with for get_by_kind in existing
    test — get_by_kind is now legitimately called twice (INSIGHT for gotchas, RUN for journal)
  - Header-only partial return ("## Gotchas" without blocks) returns "" rather than
    emitting a heading with no content (no orphaned headings)
metrics:
  duration: "7m"
  completed: "2026-06-08"
  tasks_completed: 2
  files_changed: 2
---

# Phase 07 Plan 02: Gotchas Prefix Layer Summary

Adds the `## Gotchas` context prefix layer to `build_context_prefix`, positioned between pack and memory, with full budget participation matching the Phase-6 CR-01 fix for since-last-run.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add gotchas config helpers + _read_gotchas_layer | 36bd3b4 | flowstate/context_prefix.py |
| 2 | Wire gotchas_layer into assembly, fit-ladder, budget guard | ff0e8c9 | flowstate/context_prefix.py, tests/test_context_prefix.py |

RED commit: 99c2a89

## What Was Built

**Task 1 — Config helpers + layer reader:**
- `_DEFAULT_GOTCHAS_MAX_ENTRIES = 10`, `_DEFAULT_GOTCHAS_BUDGET_TOKENS = 1500` module constants
- `_load_gotchas_max_entries(root)` — key `gotchas_max_entries`, default 10, `isinstance(int) and not isinstance(bool) and >0` guard
- `_load_gotchas_budget_tokens(root)` — key `gotchas_budget_tokens`, default 1500, same guard
- `_load_gotchas_enabled(root)` — key `gotchas_enabled`, default `True`; accepts only real `bool`, non-bool falls back to default
- `_read_gotchas_layer(root, memory)` — fetches `MemoryKind.INSIGHT` with `"gotcha"` tag filter, two-pass stable sort (last_seen desc, then count desc), caps to max_entries, greedy token-budget trim, returns `""` when disabled/empty/raises, never raises

**Task 2 — Assembly wiring:**
- `gotchas_layer = _read_gotchas_layer(root, memory)` built before the pack fit-ladder
- Both pack fit-ladder candidates (`candidate` and `candidate2`) now include `gotchas_layer` in their token estimate — CR-01 fix applied
- Final budget guard: drop `since_last_run_layer` first (most dynamic), then `gotchas_layer` if still over; both logged via Rich console, never silent
- Final assembly list: `[fixtures_layer, pack_layer, gotchas_layer, memory_layer, since_last_run_layer]`
- Docstring updated: 5 layers documented

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed assert_called_once_with regression in existing test**
- **Found during:** Task 2 full test run
- **Issue:** `test_since_last_run_respects_limit_from_config` used `assert_called_once_with(MemoryKind.RUN, limit=2)` which assumed `get_by_kind` was called exactly once. After Task 2, `_read_gotchas_layer` also calls `get_by_kind(MemoryKind.INSIGHT, ...)`, so the count became 2.
- **Fix:** Changed `assert_called_once_with` → `assert_any_call` with updated docstring clarifying both calls are expected.
- **Files modified:** `tests/test_context_prefix.py`
- **Commit:** ff0e8c9

## Success Criteria Verification

- [x] `## Gotchas` appears before `## Prior Knowledge` and after pack layer
- [x] Layer capped by `gotchas_max_entries` (default 10) and `gotchas_budget_tokens` (default 1500)
- [x] `gotchas_enabled=false` omits section entirely
- [x] `gotchas_layer` joins BOTH pack fit-ladder candidate token estimates
- [x] `gotchas_layer` joins the final budget guard (drop-with-log)
- [x] No bridge import: `grep -c 'import.*bridge' flowstate/context_prefix.py` == 0
- [x] Layer never raises (`try/except` wraps entire body)
- [x] Tests pass: 479 passed, coverage 92.23% ≥ 80%, ruff clean

## Self-Check: PASSED

Files exist:
- `flowstate/context_prefix.py` — FOUND
- `tests/test_context_prefix.py` — FOUND

Commits exist:
- 99c2a89 (RED) — FOUND
- 36bd3b4 (GREEN Task 1) — FOUND
- ff0e8c9 (GREEN Task 2 + fix) — FOUND
