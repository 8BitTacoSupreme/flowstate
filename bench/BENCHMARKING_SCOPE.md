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

## Dead-alias table

| old key | maps to | what it actually is |
|---|---|---|
| `autoresearch` | `research` | split-topic `claude --print` calls |
| `gstack` | `strategy` | one `claude --print` pressure-test call |
| `superpowers` | `discipline` | pure-Python git/tests/hooks audit — **ZERO LLM calls** (`flowstate/discipline.py:1` docstring: "Discipline module — pure Python project audit (replaces superpowers.py).") |

Source: `flowstate/state.py:63-65` (`_OLD_TOOL_KEYS`). These keys are **deleted on state
migration**, asserted at `tests/test_state.py:92-94`.

State plainly: an external review mistook these three dead aliases for a three-tier
"Cialdini persuasion / trust-boundary / deep-domain-hunting" compliance architecture.
**No such layers exist**; none are installed as skills or plugins. `flowstate/`'s only
enforcement primitive is `flowstate/verify.py`'s mechanical acceptance gates (coverage
threshold + produced-artifact integrity, `flowstate/verify.py:57-129`) — everything else
honestly SKIPs.

---

## Integrity rules

- Never cite a Track-1 number to license a Track-2 claim, or vice versa.
- Never quote a harness-value number as if token/cost/latency accounting existed — it
  does not; `prefix_tokens` is a `len()//4` estimate, not measured usage.
- Never present the dead-alias trio (`autoresearch`/`gstack`/`superpowers`) as an
  architecture — they are deleted-on-migration state keys, nothing more.
- Name the track alongside every metric ("Track 1: recall_all@5 = 0.866" not just
  "0.866").
