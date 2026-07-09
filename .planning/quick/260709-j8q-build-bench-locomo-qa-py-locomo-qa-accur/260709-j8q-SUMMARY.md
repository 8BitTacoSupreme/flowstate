---
phase: quick-260709-j8q
plan: "01"
status: complete
subsystem: bench
tags: [locomo, qa-accuracy, string-metrics, tdd]
dependency_graph:
  requires: [bench.locomo, bench._retrieval, bench.grounding]
  provides: [bench.locomo_qa]
  affects: []
tech_stack:
  added: []
  patterns: [module-attribute-imports, porter-approx-stem, wilson-ci, mass-failure-guard]
key_files:
  created:
    - bench/locomo_qa.py
    - tests/test_locomo_qa.py
decisions:
  - "Oracle arm skips empty-evidence QA items (including cat-5 adversarial with no evidence)"
  - "Mass-failure guard counts only reader_empty (no judge in string-metric path)"
  - "id_to_text dict removed from _run conv loop — _build_context handles the lookup internally"
metrics:
  duration: ~8 min
  completed: "2026-07-09"
  tasks_completed: 2
  files_changed: 2
---

# Quick Task 260709-j8q: LoCoMo QA-accuracy harness

LoCoMo QA harness with official string metrics (token-overlap F1 + exact-match + cat-5 adversarial rule), no LLM judge, retrieval + oracle arms, and mass-failure guard.

## What Was Built

`bench/locomo_qa.py` — LoCoMo QA-accuracy evaluator that mirrors `longmemeval_qa.py` but replaces the LLM judge with deterministic string metrics:
- `_normalize` / `_stem` (Porter-approx, zero deps) / `_f1` / `_exact_match` / `_score_item`
- Category-5 adversarial rule: phrase-match for "no information available" / "not mentioned"
- `_answer_one`: claude via `_g._answer`; openai via lazy `_openai_chat` (max_retries=10, timeout=120)
- `_run`: retrieval + oracle arms; per-category (1-5) and overall F1/EM + Wilson CI on EM rate
- Oracle arm skips empty-evidence QA items (counted as `oracle_skipped`)
- Mass-failure guard: `reader_empty / total > max_failure_rate (0.30)` → exit 2 + `unreliable:true`
- Seeded `--sample`/`--seed`, `--limit`, openai prereq hard-check + per-model canary probe
- Module-attribute imports (`import bench._retrieval as _r` etc.) for clean monkeypatching

`tests/test_locomo_qa.py` — 32 offline tests; inline INTEGER-category fixture (cat-1, cat-2, cat-5 adversarial, empty-evidence) — does not touch `bench/fixtures/locomo_smoke.json`.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `5067807` | test (RED) | Failing tests for LoCoMo QA harness |
| `597579e` | feat (GREEN) | Implement bench/locomo_qa.py |

## Verification

- `python -m pytest tests/test_locomo_qa.py -q` → 32 passed
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80` → 928 passed, 91.9% coverage
- `ruff check bench/locomo_qa.py tests/test_locomo_qa.py` → clean
- `ruff format --check bench/locomo_qa.py tests/test_locomo_qa.py` → clean
- `python -c "import bench.locomo_qa"` → exit 0
- `git diff --stat HEAD~2 HEAD` → only 2 new files, no other modifications

## Deviations from Plan

**1. [Rule 1 - Bug] Removed unused `id_to_text` dict from `_run` conv loop**
- Found during: GREEN phase ruff check
- Issue: `id_to_text` was computed but never used — `_build_context` handles the lookup internally
- Fix: Removed the dead assignment
- Files: `bench/locomo_qa.py`

## Self-Check: PASSED

- `bench/locomo_qa.py` — created and committed at `597579e`
- `tests/test_locomo_qa.py` — created and committed at `5067807`
- 32 tests pass; ruff clean; import without openai works; only 2 new files in diff
