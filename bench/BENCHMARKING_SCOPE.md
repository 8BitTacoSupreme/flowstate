# Benchmarking Scope — Two-Track Model

**Date:** 2026-07-10 · Purpose: prevent citing a Track-1 (retrieval-ranking) number to
license a Track-2 (harness-value) claim, or vice versa.

Everything below is measured, not estimated. See `BENCHMARK_HANDOFF.md` for the full
Track 1 measured-results record, and `PAIRED_DESIGN_RUNBOOK.md` for the Track 2
harness-value experiment protocol and status.

---

## Track 1 — Retrieval component

**Files:** `bench/longmemeval.py`, `bench/locomo.py`, shared `bench/_retrieval.py`.
**Metrics:** `recall_all@k`, `recall_any@k`, evidence-coverage.

**ZERO LLM involvement — fully deterministic.** No `claude --print` call anywhere in
this track; scores are computed from embedding/BM25 rankings against gold evidence sets.

Critical framing: BM25 here is the **INCUMBENT** implementation, not an arbitrary
external baseline. v0.6.0 replaced FTS5/BM25 with semantic KNN inside
`MemoryStore.get_context()` (`flowstate/memory.py`, `_semantic_results` at line 618,
`_SEMANTIC_MAX_DISTANCE = 0.89` at line 44, ≈ cosine 0.60). So semantic-vs-BM25 in this
track is the counterfactual for a change already shipped in production — not a
speculative comparison.

**What Track 1 licenses:** claims about retrieval ranking quality ONLY — which backend
surfaces the right evidence at which rank.

**What Track 1 cannot license:** any claim about output quality, whether a user's
question gets answered better, or the value of FlowState's context-assembly harness.
Retrieval-ranking numbers say nothing about downstream answer quality.

### Measured (n=500, real `longmemeval_s_cleaned.json`)

| config | recall_all@5 | recall_all@10 | recall_any@5 |
|---|---|---|---|
| BM25 | 0.844 | 0.904 | 0.966 |
| semantic bge-small, chunked (400 tok) | 0.866 | 0.946 | 0.966 |

Wilson CIs for recall_all@5 overlap (`[0.810,0.873]` BM25 vs `[0.833,0.893]` semantic) —
no paired significance test (McNemar / paired bootstrap) has been run yet. `recall_any@5`
is identical (0.966) for both backends. Full table incl. LoCoMo: `BENCHMARK_HANDOFF.md` §2.

---

## Track 2 — Harness value

**Files:** `bench/compound_eval.py`, `bench/replicate.py`, `bench/metrics.py`,
`bench/judge.py`, `bench/report.py`.

**Arms** via `_LAYERS_MAP` (`bench/compound_eval.py:60-66`):

| arm | layers | meaning |
|---|---|---|
| `full` | `None` (all layers) | current production prefix |
| `none` | `frozenset()` | vanilla control |
| `pack` | `{"fixtures","pack"}` | naive code RAG |
| `memory` | `{"gotchas","memory","since_last_run"}` | compounding |
| `wiki` | `{"fixtures","wiki"}` | distilled knowledge |

`bench/metrics.py` computes the **AUTHORITATIVE** 4-axis `CompoundingScore`
deterministically — its only imports are `dataclasses`, `itertools.pairwise`,
`typing.Literal` (stdlib, no LLM). The single "judge" match in that file is the English
word in its line-6 module docstring, not a call site.

The LLM judge is **Tier-2 and EXPLICITLY EXCLUDED** from the mechanical score:
`bench/report.py:80` emits `"note": "Tier-2 output-quality judge — EXCLUDED from
compounding_score"`.

**What Track 2 licenses:** whether the context stack improves output quality per token
spent — the harness-value question.

**What Track 2 cannot license:** any claim about retrieval ranking; Track 2 never
measures recall/precision against gold evidence sets.

---

## Known state to record honestly

- **The harness-value experiment already ran and came back NULL.** Cohen's d 0.29 at
  K=3/N=5; the K=8/N=10 d=0.62 was a run-0 noise artifact — in absolute quality the
  control arm ended HIGHER (off 7.6 vs on 7.0). See `PAIRED_DESIGN_RUNBOOK.md` "Why this
  run (context)".
- **No token, cost, or latency accounting exists anywhere in `bench/`.**
  `prefix_tokens` (`bench/metrics.py:51`, `bench/capture.py:186`) is
  `len(prefix) // 4` — an input-context size *estimate*, not measured consumption.
  `ClaudeBridge.run()` accepts `output_format="json"` (`flowstate/bridge.py:197,230`)
  and its module docstring cites `usage.cache_read_input_tokens` (`flowstate/bridge.py:16`),
  but no caller ever passes `output_format="json"` for usage extraction and
  `BridgeResult` has no `usage` field — its fields are `success, output, exit_code, error`
  (`flowstate/bridge.py:105-109`).
- **Evaluator independence is not enforced.** `bench/judge.py` shells out to `claude`
  (deliberately NOT `flowstate.bridge`) to grade artifacts that `flowstate.bridge`
  produced via `claude`. Nothing requires judge-model ≠ producer-model.

---

## Renamed-adapter table — what the names promise vs what the code does

> **ERRATUM (2026-07-10).** An earlier revision of this section called `autoresearch` /
> `gstack` / `superpowers` "dead aliases" and asserted that "no such layers exist." **That
> was wrong.** All three are real, well-known upstream projects, and FlowState's own README
> credits them as the explicit inspirations for its `research` / `strategy` / `discipline`
> adapters. The v0.1.0 tool keys were *named after* them. The v0.2.0 rename genericized the
> names; it did not delete a fiction. The corrected statement is below.

| v0.1.0 key | renamed to | upstream project | what upstream does | what FlowState's adapter does |
|---|---|---|---|---|
| `autoresearch` | `research` | [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | propose → run → **measure** → keep/discard on validation loss; `program.md` carries instructions + constraints + stopping criteria | fan-out one `claude --print` call per comma-separated topic, concatenate. **No loop, no measurement, no keep/discard.** |
| `gstack` | `strategy` | [garrytan/gstack](https://github.com/garrytan/gstack) | 23 role-skills; `/office-hours` = six forcing questions; CEO/eng/design reviews; `/cso` OWASP+STRIDE | one `claude --print` call with a 5-point prompt. **No scoring, no rubric, no gate.** |
| `superpowers` | `discipline` | [obra/superpowers](https://github.com/obra/superpowers) | mandatory RED-GREEN-REFACTOR; *"deletes code written before tests"*; git worktrees; skills | seven `Path.exists()` checks. **`success=True` is hardcoded** (`flowstate/discipline.py:56`) and `orchestrator.py:315-319` marks the step COMPLETED without ever reading `.checks`. **Enforces nothing; cannot fail.** |

Sources: `flowstate/state.py:63-65` (`_OLD_TOOL_KEYS`); keys are deleted on state migration
(`tests/test_state.py:92-94`). The adapters' own docstrings are candid — `research.py:7`:
*"this is NOT Karpathy's autoresearch"*; `strategy.py:6`: *"this is NOT using Gstack slash
commands."*

**What remains true about the external review's claims.** None of the three upstream tools is
installed in this environment, and `flowstate/` never invokes any of them — it reimplements a
thin slice of each in-process. So the review's *operational* claims have no referent here:
there is no Cialdini/persuasion layer, no pressure-scenario framework, no mandatory
skill-check, and no trust-boundary gate that halts a pipeline. (Neither upstream Superpowers
nor Gstack mentions Cialdini either.) `flowstate/`'s only enforcement primitive is
`flowstate/verify.py`'s mechanical acceptance gates (coverage threshold + produced-artifact
integrity, `flowstate/verify.py:57-129`) — everything else honestly SKIPs.

**What the review got right, and this doc originally missed.** If FlowState's "execution
enforcement" layer is `discipline.py`, then it enforces nothing and cannot fail — so a
benchmark of compliance/enforcement would indeed measure nothing. The names are, at present,
close to strings. Closing that gap is the subject of the v0.6.1 milestone (see
`.planning/seeds/`), which must land **before** any further harness benchmarking.

---

## Integrity rules

- Never cite a Track-1 number to license a Track-2 claim, or vice versa.
- Never quote a harness-value number as if token/cost/latency accounting existed — it
  does not; `prefix_tokens` is a `len()//4` estimate, not measured usage.
- Never describe FlowState's `research`/`strategy`/`discipline` adapters as if they *were*
  Autoresearch / Gstack / Superpowers. They are named after those projects and implement a
  thin slice of each; the adapters' own docstrings say so. Equally: never assert the upstream
  projects are fictional — they are real, credited in the README, and this doc got that wrong
  once already (see the erratum above).
- Never present a step as passing when its success flag is hardcoded (`discipline.py:56`).
  Until v0.6.1 lands, "Discipline: completed" in `flowstate status` carries no information.
- Name the track alongside every metric ("Track 1: recall_all@5 = 0.866" not just
  "0.866").
