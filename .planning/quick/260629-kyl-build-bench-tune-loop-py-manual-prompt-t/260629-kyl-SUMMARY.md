---
phase: quick-260629-kyl
plan: 01
status: complete
subsystem: bench
tags: [tdd, bench, tune-loop, prompt-tuning, offline-tests]
dependency_graph:
  requires: [bench.grounding, bench.judge]
  provides: [bench.tune_loop]
  affects: []
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, never-raises sentinel, SimpleNamespace adapter]
key_files:
  created:
    - bench/tune_loop.py
    - tests/test_tune_loop.py
  modified: []
decisions:
  - judge_models asymmetry: _mine_failures gets split LIST; _gate SimpleNamespace gets raw COMMA STRING
  - no --apply flag: loop hard-stops at tune_report.md; human applies manually
  - disclaimer in both module docstring and emitted .md (verbatim exact string)
metrics:
  duration: ~20m
  completed: 2026-06-29
  tasks: 2
  files: 2
---

# Quick Task 260629-kyl: Build bench/tune_loop.py — Manual Prompt-Tuning Loop

Manual prompt-tuning loop that mines probe failures, proposes ONE candidate instruction via
a single `claude --print` call, gates it through `bench.grounding._run_promptab`, and emits
a human-approval report (tune_report.json + tune_report.md) — then hard-stops.

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | RED: Failing offline tests | 20a0afd | tests/test_tune_loop.py (+508 lines) |
| 2 | GREEN: Implement bench/tune_loop.py | a22087d | bench/tune_loop.py (+459 lines) |

## What Was Built

**`bench/tune_loop.py`** — New file. Implements the full prompt-tuning arc step 3:

- `_mine_failures(root, probes, base_instruction, arm, answer_model, judge_models: list)`: loops
  probes, builds context prefix via `MemoryStore` + `build_context_prefix`, evaluates each answer
  with majority-vote factchecking, returns list of failure dicts.
- `_propose_candidate(base_instruction, failures, model)`: builds a structured prompt presenting
  the current instruction and each failure case; single `claude --print` call; never raises.
- `_gate(root, probes, base_text, candidate_text, arm, answer_model, judge_models: str, trials, work_dir)`:
  writes instruction files, builds `types.SimpleNamespace` with exact attributes `_run_promptab`
  expects, reads back the gate.json verdict.
- `_emit_report(work_dir, base_text, candidate_text, failures, gate, arm)`: emits
  tune_report.json + tune_report.md. Both the module docstring and the .md contain the exact
  disclaimer: "This tool does not modify any source files. Apply manually after human review."
- `run_tune_loop(args)`: orchestrates the full loop; handles no-failures and no-candidate paths
  (both return 0 with a NO_CANDIDATE report); never raises.
- `_build_parser()` / `main()`: CLI with --root/--probes/--base-instruction/--arm/--answer-model/--judge-models/--trials/--out-dir.

**`tests/test_tune_loop.py`** — 23 offline tests, all boundaries monkeypatched (no real claude binary, no network).

## Key Decisions

**judge_models asymmetry (ON PURPOSE):**
`_mine_failures` receives the SPLIT list (loops it for `_factcheck` calls). `_gate` receives the
raw COMMA STRING (passes it to the SimpleNamespace for `_run_promptab`, which splits it itself).
`run_tune_loop` uses `judge_list` for `_mine_failures` and `args.judge_models` for `_gate`.

**No `--apply` flag:**
The loop is a pure lab tool. It emits a report and stops. Source files are never touched.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `pytest tests/test_tune_loop.py --no-cov`: 23 passed
- `pytest tests/ --cov=flowstate --cov-fail-under=80`: 803 passed, 92.02% coverage
- `ruff check bench/tune_loop.py tests/test_tune_loop.py`: clean
- `ruff format --check bench/tune_loop.py tests/test_tune_loop.py`: clean
- `git diff --quiet -- bench/grounding.py`: UNCHANGED
- `git diff --quiet -- flowstate/`: UNCHANGED

## TDD Gate Compliance

- RED commit: 20a0afd (`test(260629-kyl-01): add failing tests...`)
- GREEN commit: a22087d (`feat(260629-kyl-01): implement bench/tune_loop.py...`)
- Both gates present in order.

## Self-Check: PASSED

- bench/tune_loop.py: FOUND
- tests/test_tune_loop.py: FOUND
- Commit 20a0afd: FOUND
- Commit a22087d: FOUND
