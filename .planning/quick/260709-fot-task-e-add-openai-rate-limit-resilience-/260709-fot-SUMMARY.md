---
phase: 260709-fot
plan: "01"
status: complete
subsystem: bench
tags: [openai, retry, rate-limit, mass-failure-guard, tdd]
dependency_graph:
  requires: []
  provides: [openai-retry-resilience, mass-failure-guard]
  affects: [bench/longmemeval_qa.py]
tech_stack:
  added: []
  patterns: [sdk-retry, failure-rate-guard]
key_files:
  created: []
  modified:
    - bench/longmemeval_qa.py
    - tests/test_longmemeval_qa.py
decisions:
  - "Use OpenAI SDK built-in retry (max_retries=10, timeout=120.0) rather than a hand-rolled sleep loop — SDK honors Retry-After headers with exponential backoff + jitter"
  - "Mass-failure guard tallies judge_none + reader_empty as independent signals; failure_rate = (sum) / max(1, total_n); threshold tunable via --max-failure-rate (default 0.30)"
  - "Return exit code 2 (not 1) for unreliable runs so callers can distinguish rate-limit failure from zero-scored runs (exit 1) and success (exit 0)"
  - "Additive JSON keys (unreliable, failure_rate, judge_none, reader_empty) always present — zero-failure path gets unreliable=False and failure_rate=0.0 with no accuracy math change"
metrics:
  duration: "~6 minutes"
  completed: "2026-07-09"
  tasks_completed: 2
  files_changed: 2
---

# Phase 260709-fot Plan 01: OpenAI Rate-Limit Resilience Summary

**One-liner:** SDK retry client (max_retries=10, timeout=120.0) + mass-failure guard (exit 2 + unreliable:true JSON) protecting against silent fake scores from low-TPM 429 throttling.

## What Was Built

### Task 1 — RED (test/260709-fot-01 @ 7596a75)

Extended `tests/test_longmemeval_qa.py` with four failing tests:
- `test_openai_chat_retry_client_kwargs`: fake openai module injected via `sys.modules`; asserts `max_retries=10` and `timeout=120.0` recorded on `OpenAI()` construction.
- `test_run_qa_guard_triggers_above_threshold`: monkeypatched `_judge_one` → None for all 4 items; asserts rc==2, `unreliable:true`, `failure_rate>0.30`, WARNING containing "UNRELIABLE" in stdout.
- `test_run_qa_guard_clean_run_unreliable_false`: all judge True; asserts rc==0, `unreliable:false`, `failure_rate==0.0`, accuracy==1.0.
- `test_run_qa_guard_threshold_boundary`: 2/5 None judges (rate 0.4), `max_failure_rate=0.5`; asserts rc==0, `unreliable:false`.

Also updated `_make_args` to include `max_failure_rate` (default 0.30) — required coupling so existing `_run_qa` tests don't AttributeError after Task 2.

### Task 2 — GREEN (feat/260709-fot-01 @ 1dd0d9c)

Modified `bench/longmemeval_qa.py`:

**Change 1 — SDK retry client:**
- Added `_OPENAI_MAX_RETRIES = 10` and `_OPENAI_TIMEOUT = 120.0` module constants.
- `_openai_chat` now constructs `openai.OpenAI(max_retries=_OPENAI_MAX_RETRIES, timeout=_OPENAI_TIMEOUT)`. Lazy import and never-raises properties preserved.

**Change 2 — Mass-failure guard in `_run_qa`:**
- Run-level `judge_none_count` and `reader_empty_count` counters initialized before the arm loop.
- Inner scoring loop tallies each signal independently (both may fire for the same instance).
- After `total_n`: `failure_rate = (judge_none + reader_empty) / max(1, total_n)`, `unreliable = failure_rate > args.max_failure_rate`.
- Output dict gains four additive keys: `unreliable`, `failure_rate`, `judge_none`, `reader_empty`. JSON is always written (even when unreliable).
- Return logic: `total_n == 0 → 1` (unchanged), `unreliable → print WARNING + return 2`, else `return 0`.

**Change 3 — CLI arg:**
- `--max-failure-rate` added to `_build_parser` (type=float, default=0.30, dest=max_failure_rate).

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/test_longmemeval_qa.py -q` | 36 passed |
| `pytest tests/ --cov=flowstate --cov-fail-under=80` | 896 passed, 92.07% |
| `ruff check bench/longmemeval_qa.py tests/test_longmemeval_qa.py` | All checks passed |
| `ruff format --check` (both files) | Already formatted |
| `python -c "import bench.longmemeval_qa"` (no openai) | OK (lazy import preserved) |
| `git diff --name-only <base> HEAD` | Only 2 target files changed |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 7596a75 | test | RED — failing tests for retry-client kwargs and mass-failure guard |
| 1dd0d9c | feat | GREEN — SDK retry client + mass-failure guard implementation |

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
The OpenAI API surface already existed; this change only improves retry behavior at that existing boundary (T-fot-01) and adds result labeling (T-fot-02).
