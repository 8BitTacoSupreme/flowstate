---
phase: 20-evaluator-independence
reviewed: 2026-07-11T07:07:22Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - bench/judge.py
  - bench/compound_eval.py
  - bench/replicate.py
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: clean
---

# Phase 20: Code Review Report

**Reviewed:** 2026-07-11T07:07:22Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the three source files changed in Phase 20 (Evaluator Independence): `bench/judge.py`
(guard + multi-judge aggregation), `bench/compound_eval.py` (guard wired at the chokepoint),
and `bench/replicate.py` (distinct models threaded through the conduit).

**All five stated Critical contracts hold:**

1. `judge_run` / `summarize` / `JudgeResult` are byte-identical — the diff is purely additive
   (`_validate_judges`, `aggregate_judges`, CLI). No `raise` was introduced into `judge_run`;
   its never-raise → None path is untouched.
2. The guard is structurally ordered correctly: `_validate_judges` checks `if not judge_models:
   raise` FIRST, so the empty-set branch fires before the `judge == producer` comparison. In
   `compound_eval.main` an absent `--judge-model` becomes `[]` (`[args.judge_model] if
   args.judge_model else []`), so the "None trap" is genuinely impossible on the empty path, and
   the guard runs before `_real_loop`/the bridge check. `replicate._run_trial` threads a distinct
   pair (`claude-opus-4-1` / `claude-sonnet-4-5`) so the default real path stays runnable.
3. `_wilson` is reused via a FUNCTION-SCOPE import inside `aggregate_judges` (judge.py:211); no
   module-top `from bench.grounding` exists (grounding.py imports `_locate_claude` from judge.py,
   so a top-level import would be circular). Correct.
4. `compute_scorecard` consumes only `RunSnapshot`s; the judge output travels a separate `judged`
   list and `report.write_json` marks it `"EXCLUDED from compounding_score"`. No contamination.
5. Model-name strings are appended as discrete argv list elements in `replicate._run_trial` and
   `judge_run`; `subprocess.run(cmd, ...)` is list-form with no `shell=True`. No injection.

The one Warning below is a genuine *new* gap in the guard that the five contracts do not cover:
the real chokepoint accepts an unset producer model and silently passes validation. The Info
items are consistency/robustness notes.

## Warnings

### WR-01: `compound_eval` guard is bypassable when `--producer-model` is omitted (and the model is never bound to the real producer)

**File:** `bench/compound_eval.py:174-181, 392-404`; `bench/judge.py:178-194`
**Issue:** The real judged-run chokepoint declares `--producer-model` with `default=None` and does
NOT require it, whereas `judge.py`'s own CLI (`bench/judge.py:250-254`) makes it `required=True`.
The weaker requirement is on the load-bearing path. Trace the omitted-producer case:

```python
# compound_eval.main, do_judge == True, operator passed --judge-model sonnet, no --producer-model
judge_models = ["sonnet"]                     # non-empty -> empty-set branch does NOT fire
_validate_judges(["sonnet"], None)            # producer_model is None
#   dupes = {m for m in ["sonnet"] if m == None} == set()  -> NO raise -> guard PASSES
```

So `--judge --allow-llm --judge-model sonnet` (producer omitted) sails through the guard and
proceeds to `_real_loop`, even though the model FlowState actually produces with could be the
very same `sonnet`. The milestone's whole purpose is a *defensible* verdict; the primary control
has a hole reachable by omitting one optional flag. Two compounding facts make this worse:

- `_validate_judges(judge_models, producer_model)` is type-annotated `producer_model: str`, but
  `compound_eval` passes `None`. There is no runtime type check (no mypy in CI), so the `== None`
  comparison silently no-ops the dupe test instead of erroring.
- `--producer-model` is decorative: it is used ONLY for the guard comparison and is never threaded
  into `run_pipeline` / the bridge that actually produces artifacts (`_real_loop` → `_run_one` →
  `orch.run_pipeline(state, root)` ignore it). So even a *present* producer value is an
  operator-declared string with no binding to the real producing model — a wrong declaration
  passes the guard while independence is actually violated.

**Fix:** Make the chokepoint reject an unset producer when judging, so the guard cannot pass on a
None producer:

```python
if do_judge:
    judge_models = [args.judge_model] if args.judge_model else []
    if args.producer_model is None:
        console.print(Panel(
            "judge configuration rejected: --producer-model is required with --judge "
            "(cannot verify independence against an unknown producer)",
            title="JUDGE CONFIG", border_style="bold red"))
        return _EXIT_JUDGE_CONFIG
    try:
        _validate_judges(judge_models, args.producer_model)
    except ValueError as exc:
        ...
```

Optionally tighten `_validate_judges`'s signature to `producer_model: str | None` and treat
`None` as an explicit hard fail there too, so the pure helper is safe regardless of caller. (The
`replicate` conduit already threads a concrete producer, so it is unaffected by this fix.)

## Info

### IN-01: `compound_eval` does not comma-split `--judge-model`; a multi-judge string degrades silently

**File:** `bench/compound_eval.py:393`
**Issue:** `judge_models = [args.judge_model] if args.judge_model else []` wraps the raw string,
so `--judge-model "sonnet,opus"` becomes the single element `["sonnet,opus"]`. `judge.py`'s CLI
(`judge.py:273`) DOES comma-split. On the chokepoint path the comma-string is passed verbatim as
`model="sonnet,opus"` to `judge_run` → `claude --model sonnet,opus` → invalid model → the
never-raise path yields a None score with no warning. The two CLIs disagree on multi-judge input
semantics.
**Fix:** Either comma-split consistently (`[m.strip() for m in (args.judge_model or "").split(",")
if m.strip()]`) or document that the chokepoint is single-judge-only and reject commas.

### IN-02: multi-judge `aggregate_judges` has no production caller

**File:** `bench/judge.py:197-242`; `bench/compound_eval.py:339-341`
**Issue:** `aggregate_judges` (the IND-02 multi-judge/Wilson surface) is exercised only by tests.
The real path (`_real_loop`) collects ONE `JudgeResult` per run via `judge_run` and reports the
across-run trend (`summarize` / `render_judge_panel`); it never aggregates multiple judges over a
single artifact. Wiring is explicitly executor discretion per the plan, so this is not a defect —
but the multi-judge Wilson pass-rate ships dormant, mirroring the WIKI-F1 "mechanism ships but
never fires" pattern. Worth a tracking note so a later phase actually routes multiple judges
through it.

### IN-03: `--producer-model` semantics are declared-only (no binding to the producing model)

**File:** `bench/compound_eval.py:174-181`; `bench/replicate.py:36-37`
**Issue:** Both callers treat the producer model as an operator-supplied label for the guard, never
as the model the pipeline uses to produce (`replicate` hardcodes `_PRODUCER_MODEL =
"claude-sonnet-4-5"` but does not force the spawned `compound_eval`/pipeline to produce with it).
This is inherent to D-06 (RunSnapshot carries no producer field), but it means the guard verifies
declared intent, not actual independence. Recommend a docstring/comment stating the guard's
guarantee is "the declared judge ≠ declared producer," not "the judge did not grade the real
producer," so future readers don't over-trust it.

### IN-04: `aggregate_judges` does not clamp scores to the documented 0–10 range

**File:** `bench/judge.py:213, 233-234`; `bench/judge.py:100-109`
**Issue:** `_parse_score` accepts any int/float (`isinstance(s, (int, float))`) with no bound, and
`aggregate_judges` feeds `scored` straight into `fmean`/`median` and the `>= _PASS_THRESHOLD`
binarization. A malformed-but-parseable judge JSON returning e.g. `"score": 100` pollutes the mean
and always counts as a pass. The prompt requests an integer 0–10 but nothing enforces it.
**Fix:** Clamp or reject out-of-range scores in `_parse_score` (e.g. `if not 0 <= s <= 10:
continue`), preserving the never-raise → None contract.

---

_Reviewed: 2026-07-11T07:07:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
