---
phase: 20-evaluator-independence
verified: 2026-07-11T00:00:00Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: initial verification
---

# Phase 20: Evaluator Independence Verification Report

**Phase Goal:** The judge can no longer silently grade its own producer's output, and a single judge call becomes a defensible multi-judge verdict — without disturbing `bench/metrics.py`'s authority.
**Verified:** 2026-07-11
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `python -m bench.judge` exits nonzero when `--judge-model` absent | ✓ VERIFIED | CLI smoke: exit=1, "no judge model configured"; `main()` catches `ValueError` → return 1 (judge.py:274-278) |
| 2 | `python -m bench.judge` exits nonzero when judge == producer | ✓ VERIFIED | CLI smoke: exit=1, dupe message; `_validate_judges` dupe branch (judge.py:189-194) |
| 3 | Distinct non-empty judge set + producer passes (exit 0) | ✓ VERIFIED | CLI smoke: exit=0, "ok: 1 judge model(s)..." |
| 4 | `_validate_judges` empty-set branch fires BEFORE any judge==producer==None comparison | ✓ VERIFIED | `if not judge_models: raise` is first (judge.py:185-188), dupe check second; compound_eval also rejects None producer first (compound_eval.py:401-410) |
| 5 | compound_eval chokepoint calls shared `_validate_judges` when `do_judge` true, before `_real_loop`/bridge | ✓ VERIFIED | Guard block at compound_eval.py:392-421, before mode dispatch (line 424); imported not duplicated (import line 46; `def _validate_judges` count = 0) |
| 6 | WR-01 fix: compound_eval rejects unset `--producer-model` when judging | ✓ VERIFIED | compound_eval.py:401-410 returns `_EXIT_JUDGE_CONFIG`; CLI smoke printed "producer-model is required" panel; test `test_compound_eval_real_judge_without_producer_model_aborts_config` (line 113) passes |
| 7 | replicate `_run_trial` threads DISTINCT judge/producer models into subprocess | ✓ VERIFIED | `_JUDGE_MODEL="claude-opus-4-1"`, `_PRODUCER_MODEL="claude-sonnet-4-5"` (replicate.py:36-37) appended to cmd (replicate.py:75-78) |
| 8 | close_loop.py gets NO direct guard (transitive via compound_eval) | ✓ VERIFIED | close_loop untouched; reaches guard through `replicate._run_trial` → compound_eval subprocess |
| 9 | `aggregate_judges` reports 0-10 mean/median AND binarized Wilson-CI pass-rate | ✓ VERIFIED | judge.py:230-242 returns mean/median/pass_rate/wilson_low/wilson_high; `_wilson` reused via function-scope import (judge.py:211) |
| 10 | Wilson reused via function-scope import; no module-top `from bench.grounding` | ✓ VERIFIED | Import inside `aggregate_judges` (judge.py:209-211); grounding.py:76 imports `_locate_claude` from judge → confirms circular-import risk avoided |
| 11 | Even-N tie = fail; single-judge default; every judge ≠ producer; documented threshold | ✓ VERIFIED | `majority_pass = passes > n/2` (judge.py:241); `_PASS_THRESHOLD=7.0` documented (judge.py:30-33); test asserts 2/4 → False |
| 12 | `summarize()`/`judge_run`/`JudgeResult` contracts unchanged (additive) | ✓ VERIFIED | judge_run signature `*, model: str \| None = None` intact; only `raise` in judge.py is in `_validate_judges` (185-194), none in judge_run body; regression test asserts summarize byte-identical |
| 13 | IND-03: test asserts compute_scorecard/compounding_score authoritative + LLM judge EXCLUDED under multi-judge | ✓ VERIFIED | `compute_scorecard(snapshots)` takes only RunSnapshots (metrics.py:158, no JudgeResult); tests `test_compounding_score_unaffected_by_multi_judge_scores` (all-0 vs all-10 → score unchanged) + `test_write_json_marks_judge_excluded_under_multi_judge` (line 248) |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bench/judge.py` | guard + CLI + aggregation + threshold constant | ✓ VERIFIED | `_validate_judges`, `main`, `__main__`, `aggregate_judges`, `_PASS_THRESHOLD` all present; ruff clean |
| `bench/compound_eval.py` | shared-guard call + `--producer-model` + WR-01 fix | ✓ VERIFIED | Guard wired (line 412), producer arg (173-180), `_EXIT_JUDGE_CONFIG=5` (line 68), None-producer reject (401-410) |
| `bench/replicate.py` | distinct judge/producer threaded into subprocess | ✓ VERIFIED | Module constants + cmd append (36-37, 75-78) |
| `tests/test_bench_judge.py` | guard + aggregation tests | ✓ VERIFIED | 39 tests pass (subset of 163) |
| `tests/test_bench_judge_independence.py` | real-guard-path + IND-03 exclusion tests | ✓ VERIFIED | 11 tests incl. real-path guard, WR-01 case, exclusion, determinism |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| compound_eval.main | bench.judge._validate_judges | guard call before _real_loop | ✓ WIRED | Imported (line 46), called (line 412) |
| replicate._run_trial | compound_eval subprocess | distinct --judge-model/--producer-model in argv | ✓ WIRED | replicate.py:75-78 |
| metrics.compute_scorecard | RunSnapshot list only | no JudgeResult input | ✓ WIRED | Signature `list[RunSnapshot]` — no judge param; exclusion tests assert |
| aggregate_judges | grounding._wilson | function-scope import | ✓ WIRED | judge.py:211 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| judge CLI absent judge-model | `python -m bench.judge --producer-model opus` | exit=1, guard message | ✓ PASS |
| judge CLI same model | `python -m bench.judge --judge-model opus --producer-model opus` | exit=1, dupe message | ✓ PASS |
| judge CLI distinct | `python -m bench.judge --judge-model sonnet --producer-model opus` | exit=0, ok message | ✓ PASS |
| compound_eval absent judge/producer | `--mode real --judge --allow-llm --root <tmp>` | JUDGE CONFIG rejection panel | ✓ PASS |
| compound_eval WR-01 (judge set, producer absent) | `... --judge-model sonnet` | JUDGE CONFIG rejection panel | ✓ PASS |
| compound_eval distinct pair | `... --judge-model sonnet --producer-model opus` | entered `_real_loop` (real bridge present, made live calls → timed out) — guard PASSED | ✓ PASS |

### Test Suite

- Targeted: `tests/test_bench_judge_independence.py tests/test_bench_judge.py tests/test_bench_compound.py tests/test_bench_replicate.py tests/test_bench_close_loop.py` → **163 passed**
- Full suite (per SUMMARY/task): 1170 passed, 91.17% coverage (≥80% gate)
- ruff: clean on all four changed files

### CONTEXT Decision Coverage (D-01 .. D-08)

The plan-time decision-coverage gate was overridden (decisions cited in plan bodies, not the structured `must_haves.truths` block). Confirmed all 8 landed in code:

| Decision | Landed | Evidence |
|----------|--------|----------|
| D-01 (0-10 + binarized Wilson pass-rate) | ✓ | `aggregate_judges` mean/median + pass_rate + wilson (judge.py:230-242) |
| D-02 (documented threshold; summarize unchanged) | ✓ | `_PASS_THRESHOLD=7.0` documented (judge.py:30-33); summarize regression test |
| D-03 (config-time hard fail; judge_run never-raise intact) | ✓ | Guard raises only in `_validate_judges`; no raise in judge_run body |
| D-04 (same/absent judge = hard stop) | ✓ | Empty-set + dupe raises; compound_eval returns _EXIT_JUDGE_CONFIG |
| D-05 (argparse `python -m bench.judge` CLI) | ✓ | `_build_parser`/`main`/`__main__` (judge.py:245-287) |
| D-06 (shared helper, producer explicit, compound_eval chokepoint, replicate conduit, close_loop transitive) | ✓ | Import not dup; replicate threads models; close_loop untouched |
| D-07 (single-judge default; every judge ≠ producer) | ✓ | `--judge-model` default None single; ANY-judge dupe check |
| D-08 (even-N tie = fail) | ✓ | `passes > n/2`; test asserts 2/4 → False |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IND-01 | 20-01, 20-02 | fails loud when judge-model absent or equals producer | ✓ SATISFIED | CLI + compound_eval guard, real-path tests, WR-01 fix |
| IND-02 | 20-01, 20-02 | multi-judge averaging (majority vote + Wilson CI) mirroring grounding | ✓ SATISFIED | `aggregate_judges` + reused `_wilson`, tie=fail |
| IND-03 | 20-02 | test asserts metrics stays authoritative, judge excluded under multi-judge | ✓ SATISFIED | determinism + all-0/all-10 invariance + EXCLUDED-note tests |

All three IDs accounted for in REQUIREMENTS.md (lines 18-20, 56-58 marked Complete); no orphaned IDs mapped to Phase 20.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| bench/judge.py | 197-242 | `aggregate_judges` has no production caller (dormant multi-judge Wilson surface) | ℹ️ Info | Explicitly executor discretion per plan (REVIEW IN-02); IND-02 unit-tested. Not a goal blocker — the phase goal is the *defensible verdict mechanism*, wiring multiple judges over one artifact is a later-phase (22) concern. |
| bench/judge.py | 100-109 | `_parse_score` does not clamp to 0-10 | ℹ️ Info | REVIEW IN-04 robustness note; never-raise contract preserved; does not affect phase-goal truths. |

No BLOCKER or WARNING anti-patterns. No TBD/FIXME/XXX debt markers in changed files.

### Human Verification Required

None. All truths are programmatically verifiable and were verified via code inspection, targeted tests, and CLI spot-checks. A real paid judged run is Phase 22 scope (out of scope here per CONTEXT).

### Gaps Summary

No gaps. The phase goal is achieved:
- The judge cannot silently grade its own producer: the shared `_validate_judges` guard fires at config time on both the `python -m bench.judge` CLI surface and the real `compound_eval` chokepoint, and the WR-01 producer-bypass (omitted `--producer-model` while judging) is now closed by an explicit None-producer hard stop at the chokepoint (compound_eval.py:401-410).
- A single judge call is now a defensible multi-judge verdict: `aggregate_judges` keeps the 0-10 mean/median and adds a binarized pass-rate with a reused Wilson CI, conservative even-N tie=fail.
- `bench/metrics.py` authority is undisturbed: `compute_scorecard`/`compounding_score` consume only RunSnapshots, and the IND-03 tests prove the score is invariant to judge scores (all-0 vs all-10) with the report's "EXCLUDED from compounding_score" note intact under the multi-judge path.

The two Info items (dormant `aggregate_judges` caller, unclamped score) are non-blocking robustness/tracking notes, one of which (dormant caller) is explicit executor discretion per the plan.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
