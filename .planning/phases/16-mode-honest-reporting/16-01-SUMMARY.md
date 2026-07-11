---
phase: 16-mode-honest-reporting
plan: 01
subsystem: bench
status: complete
tags: [bench, reporting, honesty, HAR-01]
requires: []
provides:
  - "render_report/write_json threaded with mode/arm/sample_size/producers"
  - "mode-selected caveat (cheap preserved, real emits causal note)"
  - "real-mode-no-cheap-caveat regression test"
affects:
  - bench/report.py
  - bench/compound_eval.py
tech-stack:
  added: []
  patterns:
    - "keyword-only params with cheap-compatible defaults preserve byte-identical existing callers"
key-files:
  created: []
  modified:
    - bench/report.py
    - bench/compound_eval.py
    - tests/test_bench_compound.py
decisions:
  - "Real-mode caveat/note deliberately omit the word 'cheap' so the regression test can assert absence"
  - "producers serialized as a sorted list to keep JSON deterministic"
metrics:
  duration: ~10m
  tasks: 2
  files: 3
  completed: 2026-07-10
---

# Phase 16 Plan 01: Mode-Honest Reporting Summary

Thread the actual run `mode`/`arm`/`sample_size`/producers-present through `bench/report.py` so a `--mode real` report no longer masquerades as a cheap-mode regression guard — real mode now emits a causal note and never leaks the cheap-mode caveat (HAR-01).

## What Was Built

- **`bench/report.py`**: Added `REAL_CAVEAT` constant and three helpers — `_caveat_for(mode)`, `_mode_note_for(mode)`, `_context_line(...)`. `render_report` and `write_json` gained keyword-only `mode`/`arm`/`sample_size`/`producers` params (cheap-compatible defaults). The Rich caveat panel, JSON `caveat`/`mode_note`, the trend-table title, and the markdown record are now all mode-selected. Every surface (Rich + markdown + JSON) states mode, arm, sample size (K/trials), and producers-present. `write_json` adds top-level `mode`/`arm`/`sample_size`/`producers` keys (producers sorted for determinism).
- **`bench/compound_eval.py::main`**: Computes producers-present as the sorted union of each snapshot's `layers_present`, then threads `mode=args.mode, arm=args.layers, sample_size=runs, producers=...` into BOTH the `render_report` and `write_json` call sites. No other loops/scorecard/judge logic touched.
- **`tests/test_bench_compound.py`**: Three regression tests — real-mode Rich+markdown carry no `"cheap mode"` substring and state mode/arm/K; a cheap-mode over-correction guard; a real-mode JSON test asserting `mode=="real"` with no `"cheap"` in caveat/mode_note and the new keys present.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `pytest tests/test_bench_compound.py` — 46 → 49 tests, all pass.
- Full suite: `pytest tests/ --cov=flowstate --cov-fail-under=80` — 1048 passed, 91.07% coverage.
- `ruff check` + `ruff format --check` clean on all three files.
- Existing cheap-default tests (`test_render_report_prints_caveat_and_renders`, `test_render_report_markdown_branch`, `test_cheap_dry_smoke_writes_deterministic_json`) unchanged and green — byte-identical JSON determinism preserved.

## Commits

- f79435b feat(16-01): thread mode/arm/sample_size/producers through bench report
- 10065d1 test(16-01): real-mode report never leaks cheap caveat + provenance asserts

## Self-Check: PASSED
