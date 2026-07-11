---
phase: 20-evaluator-independence
plan: 02
subsystem: bench/compound_eval
status: complete
tags: [evaluator-independence, cli-guard, chokepoint, ind-03, replicate-conduit]
requires: [bench/judge.py::_validate_judges, bench/judge.py::aggregate_judges, bench/metrics.py::compute_scorecard, bench/report.py::write_json]
provides:
  - "bench.compound_eval enforces the shared _validate_judges guard at the real judged-run chokepoint (IND-01/D-06)"
  - "bench.compound_eval --producer-model + _EXIT_JUDGE_CONFIG (fail-loud config exit)"
  - "bench.replicate threads a distinct judge/producer pair into the compound_eval subprocess (D-06 conduit)"
  - "tests/test_bench_judge_independence.py — real-guard-path + IND-03 exclusion tests"
affects: [bench/close_loop.py (guarded transitively — untouched)]
tech-stack:
  added: []
  patterns: [config-time-hard-fail-before-bridge, shared-guard-imported-not-duplicated, distinct-models-via-module-constants]
key-files:
  created: [tests/test_bench_judge_independence.py]
  modified: [bench/compound_eval.py, bench/replicate.py]
decisions:
  - "Guard fires in main() after do_judge, BEFORE mode dispatch — so it aborts without a bridge"
  - "Absent --judge-model -> empty judge list -> _validate_judges raises on the empty-set branch BEFORE any judge==producer==None comparison (D-04)"
  - "replicate models are module constants (_JUDGE_MODEL/_PRODUCER_MODEL) so _run_trial's signature stays stable and existing monkeypatch tests remain valid"
  - "close_loop.py gets NO direct guard — it never calls judge_run; covered transitively through compound_eval"
metrics:
  duration: ~10 min
  tasks: 2
  files: 3
  completed: 2026-07-11
---

# Phase 20 Plan 02: Evaluator Independence (caller wiring + IND-03) Summary

Wired the shared `_validate_judges` guard (from 20-01) into the ONE real judged-run
chokepoint — `bench/compound_eval.py` — so a live run can never grade its own producer,
threaded a distinct judge/producer pair through the `bench/replicate.py` conduit so the
default real path stays both guarded and runnable, and locked in IND-03 with tests proving
`compounding_score` stays the authoritative deterministic scorer with the LLM judge excluded.

## What Was Built

### Task 1 — Guard at the chokepoint + conduit threading (IND-01/D-06) — commit `d746596`
- `bench/compound_eval.py`: imported `_validate_judges` from `bench.judge` (NOT duplicated);
  added a `--producer-model` arg (default `None`); added `_EXIT_JUDGE_CONFIG = 5` (a distinct
  fail-loud config-error exit, separate from `_EXIT_PRODUCER_ABSENT=3` / `_EXIT_NO_BRIDGE=4`).
- In `main()`, AFTER `do_judge = _judge_allowed(...)` and BEFORE the mode dispatch: when
  `do_judge` is true, build `judge_models = [args.judge_model] if args.judge_model else []`
  and call `_validate_judges(judge_models, args.producer_model)` inside `try/except ValueError`.
  On `ValueError` it prints an operator-facing panel and `return _EXIT_JUDGE_CONFIG`. Placed
  before `_real_loop`, so it fires WITHOUT needing a claude bridge. Absent `--judge-model` →
  empty list → the guard's empty-set branch raises (D-04 hard stop) BEFORE any
  `judge==producer==None` equality comparison — the None trap is structurally impossible.
- `bench/replicate.py`: added module constants `_JUDGE_MODEL = "claude-opus-4-1"` and
  `_PRODUCER_MODEL = "claude-sonnet-4-5"` (distinct), appended `--judge-model`/`--producer-model`
  to `_run_trial`'s compound_eval subprocess `cmd`. `_run_trial`'s call-site signature is
  unchanged, so the existing whole-function / `subprocess.run` monkeypatch tests stay valid.
- `close_loop.py` untouched (guarded transitively through compound_eval — it never calls
  `judge_run`).
- New tests: direct `_validate_judges` unit tests (same-model raises, empty-set raises,
  distinct passes); REAL-guard-path caller tests via `ce.main([...])` (absent judge-model →
  `_EXIT_JUDGE_CONFIG`; judge==producer → `_EXIT_JUDGE_CONFIG`; distinct pair → passes guard,
  reaches `_EXIT_NO_BRIDGE`); a `--producer-model` parser test; a replicate-conduit distinctness
  test capturing the argv via a fake `subprocess.run`.

### Task 2 — IND-03 exclusion tests — commit `1c488b5`
- `compute_scorecard(...)` is byte-identical (`Scorecard` equality + per-axis verdicts) across
  two calls on a fixed `RunSnapshot` list — determinism, no judge input.
- `compounding_score` is invariant to multi-judge aggregate scores: `aggregate_judges` on
  all-0 vs all-10 genuinely differ (`mean`, `majority_pass`) yet the mechanical score is
  unchanged — the LLM judge (multi-judge path) is excluded from the scorer.
- `write_json` under a multi-judge result set emits the `EXCLUDED from compounding_score` note
  AND the payload's `compounding_score` equals the scorecard-only value.

## Verification

- `uv run python -m pytest tests/test_bench_judge_independence.py -q --no-cov` → 11 passed.
- `uv run python -m pytest tests/test_bench_judge_independence.py tests/test_bench_compound.py tests/test_bench_replicate.py tests/test_bench_close_loop.py -q --no-cov` → 120 passed.
- Full suite: `uv run python -m pytest tests/ -q` → 1169 passed, coverage 91.17% (≥80% gate).
- `uv run ruff check bench/compound_eval.py bench/replicate.py tests/test_bench_judge_independence.py` → clean.
- Grep gate: `_validate_judges` present in compound_eval (imported+called, 3 hits) and NOT
  redefined (`def _validate_judges` = 0); `producer-model` present in compound_eval and
  replicate; `judge-model` present in replicate; `compute_scorecard` present in the new test.

## Deviations from Plan

None — plan executed exactly as written. Both tasks are `tdd="true"`; implementation and tests
were written and verified together, committed once per task (`feat` for the caller wiring,
`test` for the IND-03 exclusion module). The pre-commit `ruff-format` hook reformatted the Task 2
test file once (whitespace only) before the successful commit.

## Notes for Downstream

- The independence guard now protects BOTH the direct `compound_eval` CLI path and the
  `close_loop → replicate → subprocess` path. Any new caller that spawns
  `python -m bench.compound_eval --judge --allow-llm` MUST pass a distinct
  `--judge-model`/`--producer-model` pair or it will abort with `_EXIT_JUDGE_CONFIG` (5).
- `_JUDGE_MODEL`/`_PRODUCER_MODEL` in `replicate.py` are placeholder-distinct aliases chosen for
  the guard's independence requirement; a real verdict run (Phase 22) should set them to the
  actual judge and producer substrate models.

## Self-Check: PASSED
- FOUND: bench/compound_eval.py, bench/replicate.py, tests/test_bench_judge_independence.py
- FOUND: commit d746596 (Task 1), commit 1c488b5 (Task 2)
