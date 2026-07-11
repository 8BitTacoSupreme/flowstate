# Phase 20: Evaluator Independence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 20-evaluator-independence
**Areas discussed:** Aggregation shape, Fail-loud boundary, Guard location, Judge set default

---

## Aggregation (IND-02: judge produces 0–10, grounding.py's Wilson CI is for booleans)

| Option | Description | Selected |
|--------|-------------|----------|
| Average scores + binarize for CI | Keep 0–10 mean/median AND binarize each judge at a threshold → pass-rate with Wilson CI. Preserves granularity summarize() trends on while mirroring grounding.py. | ✓ |
| Binarize only (literal mirror) | Collapse each 0–10 to pass/fail, majority vote, Wilson CI on pass-rate. Discards the numeric signal. | |
| Average scores only | Mean/median + stdev; no binomial Wilson CI (doesn't match SC#2 wording). | |

**User's choice:** Average scores + binarize for CI
**Notes:** Resolves the grounding.py mismatch — both the numeric mean and a binarized Wilson-CI pass-rate, not one or the other.

---

## Fail-loud boundary (IND-01: fail-loud vs judge.py's never-raise→None contract)

| Option | Description | Selected |
|--------|-------------|----------|
| Config-time hard fail, judging stays never-raise | Validate judge≠producer / judge-present BEFORE judging → raise/exit nonzero there; per-run judge_run keeps never-raise→None. | ✓ |
| Guard inside judge_run | Thread producer_model into judge_run, raise on judge==producer. Fewer call sites but breaks the never-raise contract. | |

**User's choice:** Config-time hard fail, judging stays never-raise
**Notes:** Separates operator/config error (hard stop) from runtime judging failure (soft None). Same-model judge is a hard stop, not a warning.

---

## Guard location (judge.py has no CLI today)

| Option | Description | Selected |
|--------|-------------|----------|
| Add argparse main to judge.py | `python -m bench.judge --judge-model X --producer-model Y`; guard at parse time. Matches grounding.py which is a CLI. | ✓ |
| Enforce at the caller | compound_eval.py/close_loop.py (which know producer model) call a validate helper; no new CLI. | |

**User's choice:** Add argparse main to judge.py
**Notes:** Makes IND-01's "running bench/judge.py with --judge-model" literal. Shared validation helper still called from the real-run callers (captured as D-06).

---

## Judge set default (how many judges, must each differ from producer)

| Option | Description | Selected |
|--------|-------------|----------|
| Default 1, require all ≠ producer | Backward-compatible single-judge default; every judge model must differ from producer; even-N tie = fail (conservative). | ✓ |
| Require ≥2 judges by default | Force a panel; stronger verdict but breaks single-judge callers and costs 2x+ claude calls. | |

**User's choice:** Default 1, require all ≠ producer
**Notes:** Every judge ≠ producer (not just the aggregate). Even-N ties resolve conservatively as fail.

## Claude's Discretion

Pass threshold value, validation-helper/CLI-flag names, mean vs median (or both) for the aggregate, and the exact JSON shape of the multi-judge summary.

## Deferred Ideas

None — discussion stayed within phase scope (wiki activation = Phase 21, verdict run = Phase 22).
