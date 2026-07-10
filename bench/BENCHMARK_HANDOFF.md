# Benchmark Handoff — LongMemEval & LoCoMo

**Date:** 2026-07-09 · **Branch:** `main` (pushed through `79bb782`) · **Tests:** 947 @ 91.9% coverage

Everything below is measured, not estimated. Scratchpad JSONs were ephemeral, so the numbers
are transcribed here. Reproduce with the commands in "Repro" before trusting any of it.

See `BENCHMARKING_SCOPE.md` for the two-track model (this doc is Track 1, retrieval-ranking) and `PAIRED_DESIGN_RUNBOOK.md` for the Track 2 harness-value protocol.

---

## 1. What exists

| File | Purpose |
|---|---|
| `bench/longmemeval.py` | LongMemEval retrieval: session-level `recall_all@k` / `recall_any@k` (paper's metric) |
| `bench/longmemeval_qa.py` | LongMemEval end-to-end QA: retrieve → read → judge; per-question-type + Wilson CIs |
| `bench/locomo.py` | LoCoMo retrieval: evidence-coverage + full-coverage@N; `--corpus turns\|observations` |
| `bench/locomo_qa.py` | LoCoMo QA: official stemmed-F1 + exact-match (no LLM judge) |
| `bench/_retrieval.py` | Shared backends: `bm25_rank`, `semantic_rank`, `semantic_rank_chunked` |

Supporting: `--reader-provider claude|openai`, `--judge-provider claude|openai`, seeded `--sample`,
openai retry client (`max_retries=10`), upfront **canary**, and a **mass-failure guard**
(`unreliable: true` + exit 2 rather than emitting a fake score).

---

## 2. Measured results

### LongMemEval retrieval (n=500, real `longmemeval_s_cleaned.json`)

| config | recall_all@5 | recall_all@10 | recall_any@5 |
|---|---|---|---|
| BM25 | 0.844 `[0.810, 0.873]` | 0.904 `[0.875, 0.927]` | 0.966 |
| semantic bge-small, **unchunked** | 0.806 | 0.924 | 0.934 |
| semantic bge-base, **unchunked** | 0.840 | 0.930 | 0.958 |
| **semantic bge-small, chunked (400 tok)** | **0.866** `[0.833, 0.893]` | **0.946** `[0.923, 0.963]` | 0.966 |

Our BM25 matches the paper's reported BM25 (~0.862) → the harness is faithful.

### LoCoMo retrieval (n=1,982 QA, real `locomo10.json`, top-5)

| corpus | semantic full-cov@5 | BM25 full-cov@5 |
|---|---|---|
| turns | 0.327 `[0.307, 0.348]` | **0.452** `[0.430, 0.473]` |
| **observations** | 0.459 `[0.437, 0.481]` | 0.481 `[0.459, 0.503]` |

### LongMemEval QA (n=100 seeded sample, oracle arm = gold context)

| reader / judge | oracle acc | note |
|---|---|---|
| claude-sonnet / claude | 0.410 | |
| claude-sonnet / gpt-4-turbo | 0.480 | restored oracle > retrieval ordering |
| claude-sonnet **tuned prompt** / gpt-4-turbo | 0.390 | **regression** |
| gpt-4o / gpt-4o-2024-08-06 | **0.230** | reliable run (0 failures) |
| *paper* | *0.870* | gpt-4o reader + gpt-4o judge |

---

## 3. The two bugs that mattered (root cause of the "BM25-parity" story)

1. **Truncation.** `_build_docs` embedded one vector per **whole session**, but bge models cap at
   **512 tokens**. Measured: LongMemEval sessions median **2,500 tokens**; **94.6% exceed the cap**
   (median ~2,100 tokens lost). The embedder saw ~20% of each session; BM25 indexed 100%.
   Fixed by `semantic_rank_chunked` + `--chunk-tokens` (chunk → embed → **max-sim rollup**).
   Effect: bge-small 0.806 → **0.866** recall_all@5.
2. **Wrong corpus (LoCoMo).** We retrieved over raw turns; the paper's best RAG arm used
   **observations** (assertive summaries carrying `dia_id` provenance). Fixed by `--corpus observations`.
   Effect: semantic 0.327 → **0.459** full-cov@5 (BM25 only +0.029).

**Lesson to preserve:** semantic retrieval's apparent weakness was mostly the *harness*, not the
method. BM25 nonetheless remains a strong baseline and was never decisively beaten.

---

## 4. Known defects / debt

- **`_READER_INSTRUCTION` (Task D) is a measured regression.** The "answer only from these sessions;
  say if not available" prompt makes models over-abstain. It is currently the **default reader
  prompt**. It dropped claude oracle 0.480 → 0.390 and likely depresses the gpt-4o 0.230.
  **Revert it (or gate it behind a flag) before quoting any QA number.**
- **QA judge is not the paper's.** We use a single binary `_factcheck`; the paper uses
  **per-question-type GPT-4o prompts** (published in `src/evaluation/evaluate_qa.py`). Our judge is
  almost certainly stricter/mis-calibrated.
- **Significance not established.** LongMemEval chunked-semantic (0.866) vs BM25 (0.844): Wilson CIs
  **overlap**. But these are *paired* measurements on identical instances → the correct test is
  **McNemar / paired bootstrap**, not CI overlap. Run it before claiming a win.
- **`char_budget=48000`** may truncate long gold sessions in the QA reader path — unverified.
- Session-summary corpus (LoCoMo) is intentionally excluded: plain strings, no `dia_id` provenance,
  so evidence-coverage is not computable over it.

---

## 5. Research backlog — ranked by (honest) expected value

### Tier 1 — cheap, high-confidence, no LLM spend
1. **Paired significance test** (McNemar / paired bootstrap) on chunked-semantic vs BM25 at n=500.
   Turns "leads" into "significantly beats" (or honestly kills the claim). ~1 hour, zero cost.
2. **Chunk-size sweep**: `--chunk-tokens ∈ {128, 256, 400, 512}`. We picked 400 arbitrarily.
   Also try **overlap** (stride < window) — standard and usually worth a point or two.
3. **Turn-level retrieval + `turn2session` rollup** (LongMemEval ships
   `evaluate_retrieval_turn2session`). An alternative to chunking; may beat it.
4. **Run chunked retrieval with bge-base** (we only ran chunked with bge-*small*). Unchunked
   bge-base was 0.840; chunked it should exceed 0.866.
5. **LoCoMo QA** has never been run on real data (`bench/locomo_qa.py`, string-F1, no judge → cheap).

### Tier 2 — moderate cost, high expected gain
6. **Cross-encoder reranker** (`bge-reranker-base/large`) over top-k. Directly targets the strict
   `recall_all@5`, which is where the margin is thinnest. Standard practice.
7. **Long-context embedder** (jina-embeddings-v3, nomic-embed-text — 8k tokens). Kills the
   truncation problem *and* adds capacity in one swap; no chunking needed.
8. **Bigger embedder** (bge-large 335M; Stella-V5 1.5B is what the paper's retrieval leaders used).
   Honest — just report the model. CPU embedding is brutal; wants a GPU.
9. **Hybrid BM25 + dense (RRF fusion).** Reliably beats either alone. Fine as a **bench arm**, but
   label it "hybrid" — FlowState's production path deliberately avoids lexical fusion.

### Tier 3 — QA-specific (fixes an *understated* number)
10. **Revert the Task D reader prompt** (see Defects). Free, recovers ~0.1.
11. **Adopt the paper's official reader + per-type judge prompts.** The single most honest QA move:
    score by *their* protocol rather than inventing one. Likely closes a large share of 0.230 → 0.870.
12. **Verify `char_budget`** doesn't truncate gold context in the oracle arm.
13. **Raise the OpenAI tier.** gpt-4o at Tier 1 = 30k TPM; a 100-question run needs ~1.2M tokens and
    self-paces to ~2 hours. Tier 2 ($50 cumulative + 7 days) ≈ 450k TPM → runs become trivial.

### Tier 4 — query side / speculative
14. Feed `question_date` into the query for `temporal-reasoning` items.
15. Light query expansion / HyDE.
16. Contest the scaling claims of vendor-defined benchmarks only if you intend a research piece —
    building to a competitor's self-scored benchmark validates their framing.

---

## 6. Integrity rules (do not violate for a better number)

- Never tune the judge to raise accuracy; adopt the benchmark's published judge.
- Never cherry-pick `--seed` or drop hard question types (temporal / multi-session / knowledge-update).
- Always name the metric: `recall_all@k` ≠ `recall_any@k`. Report both.
- Never compare our **retrieval-only** number against someone's **end-to-end product** number.
- A run that fails must fail loud. The `unreliable` flag + exit 2 exist because a 403 once produced a
  fake `0/100` and a 429 once produced a fake `0.14`. Both looked like real results.

---

## 7. Repro

```bash
# data (not committed; LoCoMo is CC BY-NC — do not redistribute)
python -c "from huggingface_hub import hf_hub_download as d; d('xiaowu0162/longmemeval-cleaned','longmemeval_s_cleaned.json',repo_type='dataset',local_dir='data')"
curl -sL https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json -o data/locomo10.json

# LongMemEval retrieval — the headline
python -m bench.longmemeval --data data/longmemeval_s_cleaned.json \
  --backends semantic,bm25 --k 5,10 --embed-model BAAI/bge-small-en-v1.5 \
  --chunk-tokens 400 --out lme_chunked500.json

# LoCoMo retrieval — observations corpus
python -m bench.locomo --data data/locomo10.json --backends semantic,bm25 \
  --top-n 5 --corpus observations --out locomo_obs.json

# LongMemEval QA (costs money; needs OPENAI_API_KEY for the openai providers)
python -m bench.longmemeval_qa --data data/longmemeval_s_cleaned.json \
  --backend semantic --arms retrieval,oracle --sample 100 --seed 0 \
  --judge-provider openai --judge-model gpt-4o-2024-08-06 --out qa.json
```

**Papers:** LongMemEval arxiv.org/abs/2410.10813 (retrieval baselines: Appendix E.1 / Table 8;
QA: Table 2) · LoCoMo arxiv.org/abs/2402.17753. Neither has a hosted submission leaderboard.

---

## 8. The story worth telling

Two harness bugs — truncating 94.6% of sessions past a 512-token cap, and retrieving over raw turns
instead of the benchmark's own observations corpus — made a 33M-parameter embedder look like it
merely tied BM25. Fixed, it leads on LongMemEval and ties on LoCoMo. Separately, a model-access 403
and a rate-limit 429 each produced *plausible-looking* fake scores (`0/100`, `0.14`) that a
never-raises harness reported as real.

**Measure your harness before you conclude anything about your model.**
</content>
