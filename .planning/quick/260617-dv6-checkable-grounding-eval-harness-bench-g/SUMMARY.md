---
phase: quick-260617-dv6
plan: "01"
subsystem: bench
status: complete
tags: [bench, grounding, eval, binary-judge, wilson-ci]
dependency_graph:
  requires:
    - bench.compound_eval._LAYERS_MAP
    - bench.judge._locate_claude
    - flowstate.context_prefix.build_context_prefix
    - flowstate.memory.MemoryStore
  provides:
    - bench.grounding module (grounding eval CLI harness)
    - bench/fixtures/grounding_probes.example.json
  affects: []
tech_stack:
  added:
    - bench/grounding.py (stdlib: argparse/json/math/os/re/subprocess/sys/pathlib)
  patterns:
    - Never-raises discipline throughout (mirrors bench/judge.py idiom)
    - Empty-then-good retry loop (mirrors flowstate/tools/research.py)
    - Wilson score CI (math-only, z=1.96)
    - try/finally env var save/restore in main() to prevent test pollution
key_files:
  created:
    - bench/grounding.py
    - bench/fixtures/grounding_probes.example.json
    - tests/test_bench_grounding.py
  modified: []
decisions:
  - Imported _LAYERS_MAP and _locate_claude rather than redefining (ADD-ONLY constraint)
  - main() uses try/finally to save/restore FLOWSTATE_CONTEXT_BUDGET_TOKENS so test suites are not polluted
  - Worktree was branched from eae7442 (pre-_LAYERS_MAP); merged main to fast-forward to d5570fc before task execution
metrics:
  completed_date: "2026-06-17"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
---

# Phase quick-260617-dv6 Plan 01: Checkable Grounding Eval Harness Summary

**One-liner:** Binary multi-judge grounding harness CLI (`bench/grounding.py`) with Wilson CIs, per-arm context injection via `_LAYERS_MAP`, and 12-test fully-mocked suite.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | grounding.py core + example probes fixture | 872d23a | bench/grounding.py, bench/fixtures/grounding_probes.example.json |
| 2 | Mocked test suite + env isolation fix | c2f7c51 | tests/test_bench_grounding.py, bench/grounding.py (env fix) |

## What Was Built

**`bench/grounding.py`** — argparse CLI harness:
- `_load_probes(path)` — never-raises JSON loader; returns None on missing/empty/bad input, zero subprocess calls
- `_wilson(successes, n)` — Wilson score CI at z=1.96 (stdlib math only); n==0 → (0.0, 0.0)
- `_answer(prefix, question, model)` — never-raises; retries up to 3 times (empty-then-good idiom); returns "" on all-fail
- `_factcheck(answer, ground_truth, model)` — binary YES/NO judge; None on unparseable/error; one call, no retry
- `main()` — sets `FLOWSTATE_CONTEXT_BUDGET_TOKENS` env var first (try/finally restore); non-zero on bad probes before any subprocess call; aggregates per-arm accuracy with Wilson CIs and `accuracy_delta_vs_none`

**`bench/fixtures/grounding_probes.example.json`** — 3 generic illustrative probes (CLI entry point, coverage threshold, FTS5 extension).

**`tests/test_bench_grounding.py`** — 12 test functions:
- All subprocess calls mocked; no live claude
- Covers: missing probes guard, empty/bad JSON, wilson bounds, majority vote (YES/YES/NO, NO/NO/YES, unparseable=NO), empty answer skips factcheck, retry call count, aggregation accuracy=0.5, delta_vs_none correctness, arm prefix layers_map forwarding

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Worktree missing _LAYERS_MAP (branched from older commit)**
- **Found during:** Task 1 verification
- **Issue:** Worktree branched from `eae7442`; `_LAYERS_MAP` was added in `d1fd243` between eae7442 and d5570fc (plan dispatch commit). `bench.compound_eval` in the worktree had no `_LAYERS_MAP`.
- **Fix:** Fast-forward merged `main` into the worktree branch (`git merge main --no-edit`); no conflicts.
- **Commit:** Part of the ff-merge before Task 1 commit.

**2. [Rule 1 - Bug] `main()` env var pollution across tests**
- **Found during:** Task 2 (test isolation failure — `test_bool_config_falls_back_to_default_budget` failed after grounding tests set `FLOWSTATE_CONTEXT_BUDGET_TOKENS=50000`)**
- **Issue:** `main()` set the env var unconditionally with no restore.
- **Fix:** Wrapped body in `try/finally`; saves prior value and restores (or pops) on exit.
- **Files modified:** bench/grounding.py
- **Commit:** c2f7c51

**3. [Rule 1 - Bug] `_Mem` stub missing `__init__` accepting kwargs**
- **Found during:** Task 2 (TypeError: `_Mem() takes no arguments` when `MemoryStore(root=root)` was called)**
- **Fix:** Added `def __init__(self, *args, **kwargs): pass` to the `_Mem` stub in the test.
- **Commit:** c2f7c51

## Verification Results

- **Tests:** 682 passed, 0 failed (full suite)
- **Coverage:** 92.42% (gate: ≥80%) — `--cov=flowstate --cov-fail-under=80`
- **Ruff:** `ruff check flowstate/ bench/ tests/` — clean; `ruff format --check` — clean

## Self-Check

- [x] bench/grounding.py exists and AST-parses
- [x] bench/fixtures/grounding_probes.example.json exists with 3 valid entries
- [x] tests/test_bench_grounding.py exists with 12 test functions
- [x] `_LAYERS_MAP` imported from bench.compound_eval, not redefined
- [x] `git diff main..HEAD --name-only` shows exactly 3 files (ADD-ONLY confirmed)
- [x] Commits 872d23a and c2f7c51 exist

## Self-Check: PASSED
