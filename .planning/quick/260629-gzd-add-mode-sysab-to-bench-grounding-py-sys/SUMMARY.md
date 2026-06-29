---
phase: quick-260629-gzd
plan: "01"
type: tdd
status: complete
subsystem: bench
tags: [bench, sysab, strategy, ab-testing, pairwise-judge, wilson-ci]
completed: "2026-06-29T16:30:25Z"
---

# quick-260629-gzd: sysab bench mode

Additive `--mode sysab` bench mode A/B-testing two strategy system prompts via
position-debiased pairwise generation + Wilson-CI-vs-0.5 win-rate gate.

See `260629-gzd-SUMMARY.md` for full details.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 0523a6b | test | add failing sysab tests + fixtures (RED) |
| 18bae30 | feat | implement _generate_strategy, _judge_pairwise, _run_sysab + CLI wiring (GREEN) |

## Status: complete

780 tests, 92.19% coverage, ruff clean.
