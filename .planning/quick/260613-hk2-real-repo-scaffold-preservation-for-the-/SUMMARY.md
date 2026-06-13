---
phase: quick-260613-hk2
plan: "01"
status: complete
subsystem: bench
tags: [scaffold, real-repo, compounding-eval, preservation]
requirements: [HK2-SCAFFOLD-PRESERVE]

dependency_graph:
  requires: []
  provides:
    - "scaffold() synthetic param (bench/project.py)"
    - "_real_loop synthetic=False wiring (bench/compound_eval.py)"
  affects:
    - "bench/compound_eval.py::_real_loop"
    - "bench/project.py::scaffold"

tech_stack:
  added: []
  patterns:
    - "keyword-only synthetic param with early-return on real path"
    - "contextlib.suppress for best-effort unlink"

key_files:
  modified:
    - bench/project.py
    - bench/compound_eval.py
    - tests/test_bench_compound.py

decisions:
  - "Real path = delete memory.db + immediate return; zero other mutations (no _clean_generated, no synthetic artifacts, no _seed_baseline_run)"
  - "synthetic=True default preserves byte-for-byte backward compatibility"
  - "Guard test monkeypatches bench.compound_eval.scaffold directly (module-level import binding)"
  - "Fixed existing _run_one stub to accept layers= kwarg (needed once _real_loop gained layers support)"

metrics:
  duration: "~5 minutes"
  completed: "2026-06-13"
  tasks_completed: 2
  files_modified: 3
---

# Quick Task 260613-hk2: Real-Repo Scaffold Preservation

One-liner: `scaffold(root, synthetic=False)` keyword switch preserves real kickoff (config.json, fixtures, pack, PROJECT.md, .claude/, research/) — only wipes memory.db — enabling `_real_loop` to run against a real-repo copy without destroying its kickoff prep.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add synthetic param to scaffold() + three tests | a86dd07 | bench/project.py, tests/test_bench_compound.py |
| 2 | Wire _real_loop to synthetic=False + guard test | 65fb911 | bench/compound_eval.py, tests/test_bench_compound.py |

## What Was Built

**Task 1 — bench/project.py:**
- Added keyword-only `synthetic: bool = True` to `scaffold(root)`
- `synthetic=False` path: `contextlib.suppress(Exception): (root / "memory.db").unlink(missing_ok=True)` then `return` — no other mutation
- `synthetic=True` path: unchanged byte-for-byte (entire existing body)
- Updated docstring with param documentation
- Three new tests: preservation, budget-key survival, synthetic regression guard

**Task 2 — bench/compound_eval.py:**
- Changed `scaffold(target)` → `scaffold(target, synthetic=False)` in `_real_loop` only
- `_cheap_loop`'s `scaffold(target)` left unchanged (uses synthetic=True default)
- Guard test: monkeypatches `bench.compound_eval.scaffold` + `_run_one` + `capture_run_snapshot`, calls `_real_loop(tmp_path, 1, ...)`, asserts `scaffold_calls[0]["synthetic"] is False`
- Fixed existing `test_real_loop_runs_with_monkeypatched_pipeline` stub: `lambda root, *, dry_run: None` → `lambda root, *, dry_run, layers="full": None`

## Verification

- `grep -n "synthetic=False" bench/compound_eval.py` → line 241 only (_real_loop)
- `grep -c "scaffold(target)" bench/compound_eval.py` → 1 (the bare _cheap_loop call)
- 626 tests pass, 92% coverage (≥80 required)
- ruff check + format --check: clean

## Deviations from Plan

**[Rule 1 - Bug] Fixed _run_one stub signature in existing test**
- Found during: Task 2
- Issue: Existing `test_real_loop_runs_with_monkeypatched_pipeline` stub `lambda root, *, dry_run: None` would raise TypeError when `_real_loop` calls `_run_one(target, dry_run=False, layers=layers)` — the `layers` kwarg was already present before this task
- Fix: Updated stub to `lambda root, *, dry_run, layers="full": None`
- Files modified: tests/test_bench_compound.py
- Commit: 65fb911

## Self-Check: PASSED

- bench/project.py: FOUND (scaffold has synthetic param)
- bench/compound_eval.py: FOUND (scaffold(target, synthetic=False) in _real_loop)
- tests/test_bench_compound.py: FOUND (three new scaffold tests + guard test)
- Commits: a86dd07 FOUND, 65fb911 FOUND
- Suite: 626 passed, 92% coverage
- Ruff: clean
