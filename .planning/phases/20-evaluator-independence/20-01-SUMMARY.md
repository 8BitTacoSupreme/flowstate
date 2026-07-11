---
phase: 20-evaluator-independence
plan: 01
subsystem: bench/judge
status: complete
tags: [evaluator-independence, llm-as-judge, wilson-ci, cli-guard]
requires: [bench/judge.py, bench/grounding.py::_wilson]
provides:
  - "bench.judge._validate_judges — reusable config-time independence guard (IND-01)"
  - "python -m bench.judge CLI — fail-loud validate surface (IND-01)"
  - "bench.judge.aggregate_judges — multi-judge mean/median + Wilson-CI pass-rate (IND-02)"
  - "bench.judge._PASS_THRESHOLD — documented binarization constant"
affects: [bench/compound_eval.py (Wave-2 caller reuses _validate_judges), bench/replicate.py]
tech-stack:
  added: []
  patterns: [function-scope-import-to-break-cycle, config-time-hard-fail-vs-runtime-soft-none, conservative-tie-is-fail]
key-files:
  created: []
  modified: [bench/judge.py, tests/test_bench_judge.py]
decisions:
  - "D-06 guard is pure (no I/O) so both the CLI and the Wave-2 compound_eval caller reuse it; producer passed explicitly"
  - "None per-judge scores EXCLUDED from the pass-rate denominator (an unusable judge does not vote)"
  - "_PASS_THRESHOLD = 7.0 (>= = pass); even-N tie is not a majority -> fail (D-08)"
metrics:
  duration: ~6 min
  tasks: 2
  files: 2
  completed: 2026-07-11
---

# Phase 20 Plan 01: Evaluator Independence (judge guard + aggregation) Summary

Hardened `bench/judge.py` with a fail-loud config-time independence guard (`_validate_judges` + a `python -m bench.judge` argparse CLI) and a multi-judge aggregation function that keeps the 0-10 signal (mean/median) while adding a binarized pass-rate with a reused Wilson CI — all additive, with `judge_run`/`summarize`/`JudgeResult` contracts byte-identical.

## What Was Built

### Task 1 — Independence guard + CLI (IND-01) — commit `fb9a70a`
- `_validate_judges(judge_models, producer_model) -> None`: pure (no subprocess/I/O) helper that RAISES `ValueError` on an empty judge set (D-06) or ANY judge model equal to the producer (D-04/D-07). Reusable by both the CLI and the Wave-2 `compound_eval` caller.
- `_build_parser()` + `main(argv) -> int` + `if __name__ == "__main__": sys.exit(main())`: `--producer-model` (required) and `--judge-model` (comma-list for multi-judge). Guard fires at validate time, catches `ValueError`, prints an operator-facing error, returns 1. Clean config returns 0. `python -m bench.judge` is the literal IND-01 surface.
- `judge_run`'s never-raise → None contract untouched — no `raise` added to its body (D-03).

### Task 2 — Multi-judge aggregation (IND-02) — commit `c829d38`
- `_PASS_THRESHOLD = 7.0`: named, documented module-level constant (`>=` = pass), with the D-08 tie rule commented alongside.
- `aggregate_judges(results) -> dict`: reports `mean`/`median` of per-judge 0-10 scores AND a `pass_rate` with `wilson_low`/`wilson_high`, plus `majority_pass = passes > n/2` (conservative — even-N tie fails, D-08). None scores excluded from the denominator (documented). Never raises (composes never-raise `judge_run`).
- `_wilson` reused via a FUNCTION-SCOPE import inside `aggregate_judges` — a module-top `from bench.grounding import _wilson` would create a circular import because `grounding.py` imports `_locate_claude` from `judge.py`.
- `summarize()` unchanged; a regression test asserts its output is identical for a fixed input (D-02 non-replacement).

## Verification

- `uv run python -m pytest tests/test_bench_judge.py -q --no-cov` → 39 passed (was 27; +12 new).
- `uv run ruff check bench/judge.py tests/test_bench_judge.py` → clean.
- CLI smoke: `--producer-model opus` → exit 1; `--judge-model opus --producer-model opus` → exit 1; `--judge-model sonnet --producer-model opus` → exit 0.
- Grep checks: `_validate_judges`, `def main`, `__main__`, `_PASS_THRESHOLD`, function-scope `_wilson` all present; NO module-top `from bench.grounding`; `def summarize` and `def judge_run` signatures unchanged.

## Deviations from Plan

None — plan executed exactly as written. Both tasks are `tdd="true"`; implementation and tests were written and verified together, committed once per task as `feat` (additive change to an existing module).

## Notes for Downstream (Wave 2)

- `_validate_judges` is the shared guard D-06 designates for wiring into `bench/compound_eval.py` (`--producer-model` + `do_judge` gate) and threading distinct judge/producer models through `bench/replicate.py::_run_trial`. This plan owns only `judge.py`; the caller-side wiring is a separate wave and was not touched here.
- IND-03 (test proving `compounding_score` stays deterministic / judge stays excluded under the new path) is a separate plan; `aggregate_judges` is intentionally an advisory surface, not read by `metrics.py`.

## Self-Check: PASSED
