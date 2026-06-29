---
phase: quick-260629-gzd
plan: "01"
type: tdd
status: complete
subsystem: bench
tags: [bench, sysab, strategy, ab-testing, pairwise-judge, wilson-ci]
completed: "2026-06-29T16:30:25Z"

dependency_graph:
  requires: []
  provides: [sysab-bench-mode]
  affects: [bench/grounding.py]

tech_stack:
  added: []
  patterns:
    - Position-debiased pairwise judging (both orderings per judge call)
    - Wilson-CI-vs-0.5 decision gate (ADOPT_B iff b_win_rate>0.5 AND wilson_low>0.5)
    - Never-raises pattern (every new function wraps in try/except)
    - Single-shot bridge with inject_canon=False to isolate system prompt effect

key_files:
  created:
    - bench/fixtures/strategy_scenarios.example.json
    - bench/fixtures/sys_strategy_baseline.txt
    - bench/fixtures/sys_strategy_candidate.txt
  modified:
    - bench/grounding.py
    - tests/test_bench_grounding.py

decisions:
  - inject_canon=False + max_turns=1 in _generate_strategy to isolate system prompt signal
  - Position-debiased: both orderings per (scenario, trial, judge) to cancel position bias
  - Wilson-CI-vs-0.5 gate (not CI-overlap as in promptab) because sysab uses a ratio metric

metrics:
  duration: ~10 min
  tasks_completed: 2
  files_changed: 5
  tests_added: 8
  tests_total: 780
  coverage: 92.19%
---

# Phase quick-260629-gzd Plan 01: sysab bench mode Summary

**One-liner:** Additive `--mode sysab` bench mode A/B-testing two strategy system prompts via
position-debiased pairwise generation + Wilson-CI-vs-0.5 win-rate gate.

## What Was Built

Added a fourth bench mode `--mode sysab` to `bench/grounding.py` that A/B-tests two strategy
system prompts across multiple scenarios. For each scenario it generates a strategy document per
variant (single-shot, canon-free via `_generate_strategy`), judges the two documents pairwise
with position-debiasing via `_judge_pairwise` (both orderings per judge model), and applies a
Wilson-CI-vs-0.5 win-rate decision gate in `_run_sysab` (ADOPT_B only when b_win_rate>0.5 AND
wilson_low>0.5).

Variant A defaults to the live `STRATEGY_SYSTEM_PROMPT` constant when `--variant-a` is omitted
(`is_default_prompt: true` in JSON output). The `--scenarios` flag supplies InterviewAnswers-shaped
scenario dicts; `--probes` remains required by the parser but is ignored in sysab mode.

## TDD Gate Compliance

- RED commit `0523a6b`: 8 failing tests (AttributeError on missing functions, SystemExit on
  invalid --mode choice)
- GREEN commit `18bae30`: all 58 bench tests pass; 780 total, 92.19% coverage

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 0523a6b | test | add failing sysab tests + fixtures |
| 18bae30 | feat | implement _generate_strategy, _judge_pairwise, _run_sysab + CLI wiring |

## Deviations from Plan

None — plan executed exactly as written. The ADD-ONLY constraint was honored: only one existing
line was modified (the `--mode` choices tuple extended to include "sysab"), plus one additive
dispatch line in `main()`. All other changes are purely additive.

## Known Stubs

None. The sysab mode is fully wired: scenarios load via `_load_probes`, variants are read from
files or the live constant, generation calls `ClaudeBridge`, and judging calls `subprocess.run`
via `_locate_claude()`. The bench mode requires a live `claude` binary for actual use, but all
code paths degrade gracefully (never-raises throughout).

## Threat Flags

None. This is a local bench tool with no network endpoints, no auth paths, no schema changes,
and no external-facing surface. ClaudeBridge is used in isolation mode (inject_canon=False,
no tools, max_turns=1).

## Self-Check: PASSED

- bench/grounding.py: FOUND (1082 lines, includes _generate_strategy, _judge_pairwise, _run_sysab)
- bench/fixtures/strategy_scenarios.example.json: FOUND
- bench/fixtures/sys_strategy_baseline.txt: FOUND (byte-identical to STRATEGY_SYSTEM_PROMPT)
- bench/fixtures/sys_strategy_candidate.txt: FOUND
- tests/test_bench_grounding.py: FOUND (8 new sysab tests, all GREEN)
- Commit 0523a6b: FOUND
- Commit 18bae30: FOUND
- Coverage: 92.19% >= 80% gate
