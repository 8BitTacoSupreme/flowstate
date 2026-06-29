---
phase: quick-260629-fxt
plan: 01
status: complete
type: tdd
subsystem: bench
tags: [bench, grounding, promptab, tdd, a/b-testing]
dependency_graph:
  requires: []
  provides: [bench.grounding._read_variant, bench.grounding._run_promptab, promptab-mode]
  affects: [bench/grounding.py, tests/test_bench_grounding.py]
tech_stack:
  added: [hashlib (stdlib)]
  patterns: [never-raises, Wilson-CI decision gate, instruction-kwarg A/B eval]
key_files:
  created:
    - bench/fixtures/instr_baseline.txt
    - bench/fixtures/instr_candidate.txt
  modified:
    - bench/grounding.py
    - tests/test_bench_grounding.py
decisions:
  - Added import hashlib alphabetically in stdlib imports block
  - _read_variant uses try/except returning None — mirrors never-raises pattern throughout
  - _run_promptab wraps full body in try/except returning 1 — mirrors _run_rgb envelope
  - arm guard for wikirag/wikivec happens before _LAYERS_MAP lookup to avoid KeyError
  - promptab dispatch added immediately after rgb dispatch in main() budget try-block
metrics:
  duration: ~8 minutes
  completed: 2026-06-29
  tasks: 2
  files: 4
---

# Phase quick-260629-fxt Plan 01: Add --mode promptab to bench/grounding.py Summary

**One-liner:** Additive `--mode promptab` bench mode A/B-tests two answer-instruction variants over a fixed context arm using Wilson-CI-gated ADOPT_B/NO_CHANGE decision rule.

## What Was Built

### Task 1 (RED): Fixtures + failing promptab tests

Created two fixture instruction files and 6 offline tests covering:
- `_read_variant`: happy path (stripped text) and missing file (None, no raise)
- `test_promptab_adopt_b_when_b_wins_nonoverlapping`: A=0/5, B=5/5 → non-overlapping CIs → ADOPT_B
- `test_promptab_no_change_when_tie_overlap`: both 5/5 → identical CIs → NO_CHANGE
- `test_promptab_json_shape`: verifies all required JSON keys and per-variant sub-structure
- `test_promptab_retrieval_arm_returns_1`: wikivec arm → rc=1 + note
- `test_promptab_unreadable_variant_returns_1`: missing --variant-a → rc=1 + note

### Task 2 (GREEN): Implementation

Added to `bench/grounding.py` (ADD-ONLY — no existing code modified):
- `import hashlib` (stdlib, alphabetical placement)
- `_read_variant(path: Path) -> str | None`: never-raises file reader
- `_run_promptab(args, probes) -> int`: never-raises promptab dispatcher
- `--variant-a` / `--variant-b` CLI flags (Path type, optional)
- `--mode` extended from `("layers", "rgb")` to `("layers", "rgb", "promptab")`
- dispatch branch in `main()` immediately after rgb dispatch

## Verification Gates

- `pytest tests/test_bench_grounding.py`: 50 passed (all existing RGB/layers tests unaffected)
- `pytest tests/ --cov=flowstate --cov-fail-under=80`: 92.02% coverage, 772 passed
- `ruff check bench/grounding.py tests/test_bench_grounding.py`: clean
- `ruff format --check bench/grounding.py tests/test_bench_grounding.py`: clean
- `git diff` confirms: layers arm loop, RGB code, `_answer`, `_factcheck`, `_wilson`,
  `build_context_prefix`, `context_prefix` are byte-for-byte unchanged (additions only)

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

- RED commit: `2ff1d63` — `test(quick-260629-fxt-01): add failing promptab tests and fixture files (RED)`
- GREEN commit: `03c07ae` — `feat(quick-260629-fxt-01): implement _read_variant, _run_promptab, promptab CLI flags (GREEN)`

Both gates present and in correct order.

## Self-Check: PASSED

Files verified:
- bench/fixtures/instr_baseline.txt: exists, content = "Answer concisely and specifically."
- bench/fixtures/instr_candidate.txt: exists, content = "Answer concisely and specifically. Cite the exact fact..."
- bench/grounding.py: exists, contains _read_variant and _run_promptab
- tests/test_bench_grounding.py: exists, contains 6 new promptab tests

Commits verified:
- 2ff1d63 (RED gate)
- 03c07ae (GREEN gate)
