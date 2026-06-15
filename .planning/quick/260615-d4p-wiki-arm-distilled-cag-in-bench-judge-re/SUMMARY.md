---
phase: quick-260615-d4p
plan: "01"
subsystem: bench/context_prefix
status: complete
tags: [bench, wiki, cag, judge, retry, context-prefix]
dependency_graph:
  requires: [260613-ga5]
  provides: [wiki-arm, judge-retry, wikigen]
  affects: [flowstate/context_prefix.py, bench/compound_eval.py, bench/replicate.py, bench/judge.py]
tech_stack:
  added: [bench/wikigen.py]
  patterns: [opt-in layer gate, bounded retry loop, distilled-CAG wiki]
key_files:
  created:
    - bench/wikigen.py
    - tests/test_bench_wikigen.py
  modified:
    - flowstate/context_prefix.py
    - bench/compound_eval.py
    - bench/replicate.py
    - bench/judge.py
    - tests/test_context_prefix.py
    - tests/test_bench_judge.py
    - tests/test_bench_replicate.py
decisions:
  - wiki is OPT-IN via separate wiki_included gate (include_layers is not None and "wiki" in include_layers), NOT via _included() helper which returns True for None
  - _JUDGE_MAX_ATTEMPTS=3 mirrors research.py's per-topic retry idiom
  - wikigen imports _locate_claude from bench.judge (reuse, stdlib-only dep)
  - replicate default arm list unchanged — wiki requires explicit --layers wiki
metrics:
  duration: "~15 minutes"
  completed: "2026-06-15"
  tasks: 3
  files: 7
---

# Phase quick-260615-d4p Plan 01: Wiki Arm + Judge Retry Summary

Wiki arm (distilled-CAG) added to bench and judge retry implemented to stop trial-voiding.

## What Was Built

**Task 1 — Opt-in wiki layer in context_prefix.py (e1c0f5d)**
- Added `_WIKI_PATH = ".planning/codebase/wiki.md"` constant
- Added `_read_wiki_layer(root) -> str` helper (never raises, heading-wrapped)
- Added `wiki_included = include_layers is not None and "wiki" in include_layers` gate — deliberately NOT routed through `_included()` to preserve byte-identical default
- Inserted `wiki_layer` after fixtures, before pack in all three assembly sites (candidate, candidate2, full_assembly) and final layers list
- 9 new `TestWikiLayer` tests + `_read_wiki_layer` unit tests

**Task 2 — Wiki arm wiring + bounded judge retry (c4b9dcf)**
- `compound_eval._LAYERS_MAP["wiki"] = frozenset({"fixtures", "wiki"})` added
- `--layers wiki` accepted by both compound_eval and replicate argparse
- `_JUDGE_MAX_ATTEMPTS = 3` added to judge.py
- `judge_run` now retries up to 3 times on unparseable score; subprocess exception counts as a failed attempt; never raises
- 10 new tests: call-count assertions for bad-then-good (2), first-try-good (1), all-bad (3), raise-then-good (2), early-return (0); parser + LAYERS_MAP assertions

**Task 3 — bench/wikigen.py generator (1e0ecba)**
- New `bench/wikigen.py`: `main(argv) -> int`, argparse `--root/--force/--model`
- Guards: missing pack → non-zero + message + no subprocess; existing wiki w/o --force → skip + zero + no subprocess
- Subprocess: returncode==0 + non-empty stdout → writes `wiki_path`, prints path, returns 0
- Pack truncated to `_MAX_PACK_CHARS=120000` before prompt embedding
- Subprocess raising → caught, non-zero, never raises
- `PROMPT_HEADER` constant for dense architecture wiki prompt
- `if __name__ == "__main__": sys.exit(main())` — works via `python -m bench.wikigen`
- 11 tests covering all 8 behaviors + truncation assertion + prompt header check

## Invariants Preserved

- `build_context_prefix` with NO `include_layers` (None) is byte-identical — wiki never appears on default path
- `judge_run` never raises (exception → failed attempt → retry or None-score return)
- `wikigen.main` never raises (subprocess exception caught)
- No new runtime deps; strategy/gsd adapters, RESEARCH_SYSTEM_PROMPT, _split_topics, scaffold untouched

## Verification Results

- `pytest tests/ --cov=flowstate --cov-fail-under=80` → 664 passed, 92% coverage
- `ruff check flowstate/ bench/ tests/` → all checks passed
- `ruff format --check` → 71 files already formatted

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `flowstate/context_prefix.py` → exists, contains `_WIKI_PATH`, `_read_wiki_layer`, `wiki_included`
- `bench/wikigen.py` → exists, contains `def main`, `PROMPT_HEADER`, `_JUDGE_MAX_ATTEMPTS` (in judge.py)
- `bench/judge.py` → contains `_JUDGE_MAX_ATTEMPTS = 3`
- Commits e1c0f5d, c4b9dcf, 1e0ecba → verified in git log
