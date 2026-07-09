---
phase: quick-260708-r6n
plan: 01
status: complete
subsystem: bench
tags: [tdd, bench, openai, judge, sampling, longmemeval]
dependency_graph:
  requires: []
  provides: [openai-judge-provider, seeded-sampling]
  affects: [bench/longmemeval_qa.py, tests/test_longmemeval_qa.py, pyproject.toml]
tech_stack:
  added: [openai>=1.0 (optional eval extra), random.Random seeded sampling, re._YESNO_OAI_RE]
  patterns: [lazy-import seam, attribute-access monkeypatch idiom, never-raises judge]
key_files:
  modified:
    - bench/longmemeval_qa.py
    - tests/test_longmemeval_qa.py
    - pyproject.toml
decisions:
  - GPT-4o judge uses lazy openai import so module works without SDK installed
  - provider=openai hard-stop (return 1) fires before any arm/instance loop — no silent claude fallback
  - judge_model "sonnet" auto-upgrades to "gpt-4o" when provider=openai
  - --sample applied before --limit (sample first, then cap)
  - _build_docs called twice per retrieval instance (ranking + answer context); test spy deduplicates with set()
metrics:
  duration: ~15min
  completed: "2026-07-08"
  tasks_completed: 2
  files_modified: 3
---

# Quick Task 260708-r6n: Extend bench/longmemeval_qa.py — Add GPT-4o Judge + Seeded Sampling

GPT-4o judge provider (`_judge_openai`) wired through lazy openai seam + seeded representative sampling, with provider=claude path byte-identical.

## What Was Built

Extended `bench/longmemeval_qa.py` with:

**New functions:**
- `_openai_available() -> bool` — lazy `import openai` check, never raises
- `_openai_chat(model, system, user) -> str | None` — lazy openai client call, never raises
- `_judge_openai(question, gold, answer, model) -> bool | None` — paper-style binary judge, parses yes/no via `_YESNO_OAI_RE`, never raises

**Updated `_judge_one`:**
- Added keyword-only `provider="claude"` arg (3-positional-arg call signature unchanged)
- Non-`_abs` + `provider=="openai"` → `_judge_openai`; default claude path unchanged

**Updated `_run_qa`:**
- Hard-check: `provider==openai` without `OPENAI_API_KEY` or `openai` pkg → prints message + returns 1 (no fallback)
- `judge_model` auto-upgrade: `provider=openai` + `judge_model="sonnet"` → `"gpt-4o"`
- Sampling: `random.Random(seed).sample(instances, min(sample, n))` applied before `--limit`
- Output JSON gains: `judge_provider`, `sample`, `seed`, `judge_model` (effective), `question_type_distribution`

**Updated `_build_parser`:** `--judge-provider`, `--sample`, `--seed` args added.

**pyproject.toml:** `eval = ["openai>=1.0"]` optional-dependency extra added.

## Commits

| Task | Commit | Message |
|------|--------|---------|
| RED  | ee80b24 | test(260708-r6n): add failing tests for openai judge + seeded sampling |
| GREEN | 5c9928b | feat(260708-r6n): add openai judge + seeded sampling to longmemeval_qa |
| Fix  | 50483e0 | test(260708-r6n): fix sampling spy to deduplicate _build_docs double-calls |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test spy counted double _build_docs calls**
- **Found during:** GREEN verification
- **Issue:** `_build_docs` is called twice per retrieval instance (once for ranking, once inside `_answer_one` for context). The spy in `test_run_qa_sampling_reproducible` accumulated 8 calls for 4 instances.
- **Fix:** Changed spy lists to deduplicate via `set()` (`unique_ids_run1 = sorted(set(scored_ids_run1))`).
- **Files modified:** tests/test_longmemeval_qa.py
- **Commit:** 50483e0

**2. [Rule 1 - Lint] SIM102 nested if → combined condition**
- **Found during:** GREEN ruff check
- **Issue:** `if args.judge_provider == "openai": if not (key and pkg):` triggers SIM102
- **Fix:** Combined to `if args.judge_provider == "openai" and not (key and pkg):`
- **Files modified:** bench/longmemeval_qa.py (pre-commit)

## Verification

- `python3 -c "import bench.longmemeval_qa"` passes with openai NOT installed
- `pytest tests/test_longmemeval_qa.py` → 25 passed (all offline, no keys)
- `pytest tests/ --cov=flowstate --cov-fail-under=80` → 92.07% coverage, 885 passed
- `ruff check + format --check` clean on both touched files
- `git diff bench/longmemeval.py bench/_retrieval.py bench/grounding.py flowstate/` → empty

## Known Stubs

None. All functionality wired end-to-end (judge routing, hard-check, sampling all exercised by offline tests).

## Usage Notes

`pip install -e .[eval]` adds the `openai` SDK. The `openai` package is NOT required for the test suite or the default claude provider path.
