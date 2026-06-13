---
phase: quick-260613-m60
plan: "01"
status: complete
subsystem: flowstate/tools
tags: [research, retry, resilience, bridge]
completed_at: "2026-06-13"
duration: "~5m"
tasks_completed: 1
files_changed: 2
commit: 1d8fc8d
---

# Phase quick-260613-m60 Plan 01: Research Adapter Call Resilience Summary

**One-liner:** Per-topic bridge retry loop (up to 3 attempts, max_turns=6) eliminates the ~40% "Reached max turns" placeholder failure rate in ResearchAdapter.

## What Was Built

Added bounded retry logic to `ResearchAdapter.execute`'s per-topic loop:

- `_RESEARCH_MAX_TURNS = 6` (was 3): gives the model more turns to finish searching and emit output
- `_RESEARCH_MAX_ATTEMPTS = 3`: retries each topic up to 3 times on `success=False` or blank output
- `for/else` retry loop: identical prompt/args reused across attempts (preserves prompt cache prefix); `else` clause writes the placeholder from the last attempt's `BridgeResult` only when no attempt succeeded
- `dry_run` path is byte-identical: zero bridge calls, unchanged

Six new tests added to `tests/test_tools.py`:
- `test_research_retries_then_succeeds` — fail then succeed; call count = 2
- `test_research_all_attempts_fail` — all fail; call count = `_RESEARCH_MAX_ATTEMPTS`; placeholder in report
- `test_research_first_try_success_no_retry` — succeed immediately; call count = 1
- `test_research_empty_output_is_retried` — blank output treated as failure; retried
- `test_research_uses_max_turns_six` — asserts `max_turns == _RESEARCH_MAX_TURNS == 6`
- `test_research_dry_run_zero_bridge_calls` — dry_run makes zero bridge calls

## Key Files

### Created
None.

### Modified
- `flowstate/tools/research.py` — added `_RESEARCH_MAX_TURNS`, `_RESEARCH_MAX_ATTEMPTS` constants; replaced single `bridge.run()` call with `for/else` retry loop
- `tests/test_tools.py` — 6 new resilience tests appended

## Decisions Made

- `for/else` loop pattern is idiomatic: the `else` block runs only when no `break` occurred (i.e., no attempt succeeded), keeping the placeholder write in one place with access to the last `br`
- Prompt computed once per topic before the retry loop: both the topic prompt and prior-knowledge prefix are reused verbatim across attempts, preserving Anthropic's 5-min server-side prompt cache TTL
- `br = None` initializer not needed: `for/else` guarantees `br` is set after loop (loop runs at least once since `_RESEARCH_MAX_ATTEMPTS >= 1`); Python's name resolution handles this

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- Full suite: 635 passed, 0 failed
- Coverage: 92.45% (requirement: 80%)
- ruff check: clean
- ruff format --check: clean
- `git diff --stat`: only `flowstate/tools/research.py` and `tests/test_tools.py` changed

## Self-Check

- [x] `flowstate/tools/research.py` modified with constants and retry loop
- [x] `tests/test_tools.py` has 6 new tests
- [x] Commit `1d8fc8d` exists
- [x] `_split_topics`, `_build_topic_prompt`, `RESEARCH_SYSTEM_PROMPT`, `MOCK_REPORT`, `dry_run` branch, and other adapters untouched
- [x] `max_turns=3` absent from `research.py`

## Self-Check: PASSED
