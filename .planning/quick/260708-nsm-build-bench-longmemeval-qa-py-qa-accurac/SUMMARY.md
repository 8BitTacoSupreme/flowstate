---
phase: 260708-nsm
plan: 01
type: tdd
status: complete
subsystem: bench
tags: [longmemeval, qa-accuracy, task-b, retrieval, benchmarking]
dependency_graph:
  requires: [bench/longmemeval.py, bench/_retrieval.py, bench/grounding.py]
  provides: [bench/longmemeval_qa.py, tests/test_longmemeval_qa.py]
  affects: []
tech_stack:
  added: []
  patterns: [TDD red-green, module-attribute monkeypatch seam, never-raises pattern]
key_files:
  created:
    - bench/longmemeval_qa.py
    - tests/test_longmemeval_qa.py
  modified: []
decisions:
  - Use module-attribute imports (import bench.grounding as _g) so tests can monkeypatch without re-importing
  - None judge counts as incorrect but tallied in n, matching paper semantics
  - Semantic backend resolved once per arm before instance loop for Task A parity
  - _abs suffix check for abstention is defensive; cleaned-S uses question_type="abstention"
metrics:
  duration_minutes: 22
  completed: "2026-07-08T21:25:40Z"
  tasks_completed: 2
  files_created: 2
  tests_added: 13
  coverage_after: 92.07
---

# Phase 260708-nsm Plan 01: LongMemEval QA-Accuracy Harness (Task B) Summary

Implemented bench/longmemeval_qa.py: retrieve top-k sessions via BM25 or semantic, feed context to a claude reader, judge against gold with a single binary factcheck, report per-question-type + overall accuracy with Wilson CIs.

## What Was Built

bench/longmemeval_qa.py (331 lines, ADD-ONLY):
- _reader_context: joins session texts in id order, char_budget truncation, never-raises
- _answer_one: _build_docs -> _reader_context -> _answer; "" on any failure
- _judge_one: _factcheck for normal types; _judge_rejection for _abs suffix (defensive)
- _run_qa: retrieval + oracle arms; per-type + overall accuracy + Wilson CIs; None judge = incorrect but tallied; --limit caps; semantic degrades gracefully
- _build_parser / main: full CLI

tests/test_longmemeval_qa.py (365 lines, 13 tests):
- _reader_context: ordering, char_budget, empty ids, never-raises
- _judge_one: passthrough True/False/None
- _run_qa: per-type + overall, oracle ids, limit cap, None judge, zero-scored rc, malformed skip
- main() e2e: bm25 offline (real FTS5), semantic unavailable degradation

## Deviations from Plan

None - plan executed exactly as written.

## Verification Gates

- pytest tests/test_longmemeval_qa.py -q: 13/13 passed offline
- pytest tests/ --cov=flowstate --cov-fail-under=80 -q: 873 passed, 92.07%
- ruff check + ruff format --check: both files clean
- git diff --quiet: ADD-ONLY-CONFIRMED

## TDD Gate Compliance

RED: 603d558 - 13 tests fail on ModuleNotFoundError
GREEN: 1087dce - 13 tests pass

## Self-Check: PASSED

- bench/longmemeval_qa.py: FOUND
- tests/test_longmemeval_qa.py: FOUND
- Commits 603d558, 1087dce: FOUND
