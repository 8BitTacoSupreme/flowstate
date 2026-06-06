---
phase: 04-integration-layered-cag-assembly-cache-lean-in
plan: "01"
subsystem: context-prefix
tags: [cag, context-prefix, cache, orchestrator, bridge, tdd]
dependency_graph:
  requires: [flowstate/pack.py, flowstate/context.py, flowstate/memory.py, flowstate/bridge.py]
  provides: [flowstate/context_prefix.py, build_context_prefix, ENABLE_PROMPT_CACHING_1H opt-in]
  affects: [flowstate/orchestrator.py, flowstate/bridge.py]
tech_stack:
  added: [flowstate/context_prefix.py]
  patterns:
    - most-stable-first layer ordering (fixtures → pack → memory)
    - fit→compress→omit ladder with Rich console logging (no silent truncation)
    - byte-identical-prefix-across-adapters for implicit prompt cache hits
    - opt-in env-var pattern (ENABLE_PROMPT_CACHING_1H default False)
key_files:
  created:
    - flowstate/context_prefix.py
    - tests/test_context_prefix.py
  modified:
    - flowstate/orchestrator.py
    - flowstate/bridge.py
    - tests/test_orchestrator.py
    - tests/test_bridge.py
decisions:
  - "build_context_prefix() is a single-module public function; no adapter calls it directly (built once in orchestrator, threaded via prior_knowledge seam)"
  - "_estimate_tokens uses len(text) // 4 — replicates memory.py approximation without importing it"
  - "Fixtures layer renders starter.json as compact JSON under ## Eval Fixtures with sort_keys=True for determinism"
  - "context_prefix.py imports from flowstate.pack but NEVER from flowstate.bridge — canon exclusion is a hard boundary"
  - "Budget reads .planning/config.json key context_prefix_budget_tokens; default 12000 tokens"
  - "ENABLE_PROMPT_CACHING_1H is default-False BridgeConfig flag; no unconditional env injection"
metrics:
  duration: "11m"
  completed_date: "2026-06-06"
  tasks_completed: 3
  files_changed: 6
---

# Phase 04 Plan 01: Layered CAG Assembly + Cache Lean-In Summary

**One-liner:** build_context_prefix() assembler composing fixtures → pack(fit-ladder) → memory, threaded once into all adapters via prior_knowledge, with ENABLE_PROMPT_CACHING_1H opt-in on ClaudeBridge.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 (RED) | Failing tests for build_context_prefix() assembler (17 tests) | db43939 |
| 1 (GREEN) | Implement flowstate/context_prefix.py with fit→compress→omit ladder | 508b441 |
| 2 | Thread build_context_prefix() through orchestrator prior_knowledge seam | 8873f7e |
| 3 | ENABLE_PROMPT_CACHING_1H opt-in + most-stable-first cache docs on ClaudeBridge | 048ec49 |

## What Was Built

**flowstate/context_prefix.py** (new module, 160 lines):
- `build_context_prefix(root, memory, query, *, budget_tokens=None, console=None) -> str`
- Private helpers: `_estimate_tokens`, `_load_budget`, `_read_fixtures_layer`, `_read_pack_layer`
- Layer order: `## Eval Fixtures` (starter.json compact JSON) → pack XML → `## Prior Knowledge`
- Layers joined with `\n\n---\n\n` separator; deterministic for identical inputs
- Fit ladder for pack layer only: (1) inline if fits; (2) run_pack(compress=True) retry; (3) omit + log
- Every compress/omit decision logged via Rich console — no silent truncation
- Budget from `.planning/config.json` key `context_prefix_budget_tokens` (default 12 000 tokens)
- CRITICAL: does NOT import from `flowstate.bridge`; CANON never emitted in output

**flowstate/orchestrator.py** — seam replaced:
- `prior_knowledge = memory.get_context(_pk_query) if _pk_query else ""` replaced by
  `prior_knowledge = build_context_prefix(root, memory, _pk_query, console=console)`
- Single call site: `grep -c "build_context_prefix" flowstate/orchestrator.py` = 2 (import + call)
- Seam comment updated to describe layered CAG prefix and cache behavior
- All existing tests pass unchanged in intent

**flowstate/bridge.py** changes:
- `BridgeConfig.enable_prompt_caching_1h: bool = False` — new field, default off
- `run()` sets `env["ENABLE_PROMPT_CACHING_1H"] = "1"` when flag is True
- `ClaudeBridge` class docstring: full most-stable-first layer ordering documented
  (system-prompt CANON → fixtures → pack → memory → step prompt)
- Module docstring updated to reference BridgeConfig flag
- Default behavior byte-identical to pre-change (flag defaults False)

## Test Coverage

- `tests/test_context_prefix.py`: 17 new tests — layer order, separator, canon-absent,
  no-bridge-import, fit→inline, over→compress, still-over→omit+log, byte-identical determinism,
  missing artifact combinations (all graceful)
- `tests/test_orchestrator.py`: 1 new test — build_context_prefix called exactly once;
  byte-identical string threaded to all 3 adapters (CAG-01/CAG-03 property)
- `tests/test_bridge.py`: 4 new tests — flag False (var absent), flag True (var=1),
  default False, docstring mentions cache layer ordering

**Full suite result: 367 passed, 91.46% coverage** (≥80% gate passed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test for no-bridge-import checked docstring text not just import lines**
- **Found during:** Task 1 GREEN phase (test failed because docstring mentioned "from flowstate.bridge")
- **Issue:** `inspect.getsource()` check on `"from flowstate.bridge" not in src` matched the
  docstring comment in context_prefix.py which says "must NOT import ... from flowstate.bridge"
- **Fix:** Changed test to filter lines starting with `from ` or `import ` before checking,
  so only actual import statements are inspected, not docstring text
- **Files modified:** tests/test_context_prefix.py
- **Commit:** 508b441

**2. [Rule 1 - Style] Ruff format auto-reformatted test files on each commit**
- **Found during:** Tasks 1-3 pre-commit hooks
- **Issue:** Pre-commit ruff-format hook reformatted test files on every commit (quote style, line
  breaks). Required an extra `git add + commit` cycle each time.
- **Fix:** Pre-staged the formatted files before each commit attempt; no code changes needed.

### Pre-existing Out-of-Scope Issues (deferred)

Two pre-existing ruff errors exist in files not touched by this plan:
- `tests/test_doctor.py:29` — `B017 Do not assert blind exception: Exception`
- `tests/test_repair.py:11` — `F401 MemoryStore imported but unused`

Not fixed per CLAUDE.md §3 (surgical changes). Logged here for tracking.

## Self-Check: PASSED

Files created/exist:
- [x] /Users/jhogan/frameworx/flowstate/context_prefix.py
- [x] /Users/jhogan/frameworx/tests/test_context_prefix.py
- [x] /Users/jhogan/frameworx/.planning/phases/04-integration-layered-cag-assembly-cache-lean-in/04-01-SUMMARY.md

Commits exist:
- [x] db43939 — Task 1 RED (failing tests)
- [x] 508b441 — Task 1 GREEN (implementation)
- [x] 8873f7e — Task 2 (orchestrator seam)
- [x] 048ec49 — Task 3 (cache lean-in)
