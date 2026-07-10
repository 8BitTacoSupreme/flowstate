# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- ✅ **v0.5.0 Compounding Loop** — Phases 6-8 (shipped 2026-06-09)
- ✅ **v0.6.0 Semantic Retrieval** — Phases 9-11 (shipped 2026-07-10)
- 🚧 **v0.7.0 Retrieval Benchmark Rigor** — Phases 12-17 (in progress)

## Phases

<details>
<summary>✅ v0.3.0 v2 Pivot + Operate-Safely (Phases 1-2) — SHIPPED 2026-06-06</summary>

- [x] Phase 1: Land the v2 Pivot (direct commits) — completed 2026-05-25 (b38bbd6)
- [x] Phase 2: Operate Safely (4/4 plans) — completed 2026-05-25

Full detail: [`milestones/v0.3.0-ROADMAP.md`](./milestones/v0.3.0-ROADMAP.md)

</details>

<details>
<summary>✅ v0.4.0 Context Compaction & Compounding (Phases 3-5) — SHIPPED 2026-06-06</summary>

- [x] Phase 3: Ingredients — Pack, Canon, Fixtures (3/3 plans) — completed 2026-06-06
- [x] Phase 4: Integration — Layered CAG Assembly + Cache Lean-In (1/1 plan) — completed 2026-06-06
- [x] Phase 5: UX — Guided Kickoff + Hygiene (2/2 plans) — completed 2026-06-06

Full detail: [`milestones/v0.4.0-ROADMAP.md`](./milestones/v0.4.0-ROADMAP.md)

</details>

<details>
<summary>✅ v0.5.0 Compounding Loop (Phases 6-8) — SHIPPED 2026-06-09</summary>

- [x] Phase 6: Run Journal (3/3 plans) — completed 2026-06-08
- [x] Phase 7: Gotchas Accumulator (4/4 plans) — completed 2026-06-08
- [x] Phase 8: Runnable Verification (3/3 plans) — completed 2026-06-09

Full detail: [`milestones/v0.5.0-ROADMAP.md`](./milestones/v0.5.0-ROADMAP.md)

</details>

<details>
<summary>✅ v0.6.0 Semantic Retrieval (Phases 9-11) — SHIPPED 2026-07-10</summary>

- [x] Phase 9: Embedding Provider + Vector Store Foundation (2/2 plans) — completed 2026-06-18
- [x] Phase 10: Semantic Memory Retrieval (1/1 plan) — completed 2026-06-18
- [x] Phase 11: Semantic Wiki Retrieval (1/1 plan) — completed 2026-06-18

Full detail: [`milestones/v0.6.0-ROADMAP.md`](./milestones/v0.6.0-ROADMAP.md)

</details>

### 🚧 v0.7.0 Retrieval Benchmark Rigor (In Progress)

**Milestone Goal:** Convert FlowState's "just ahead of BM25" retrieval result into a defensible, statistically significant, production-viable win — or honestly conclude it isn't there. Directly discharges v0.6.0's deferred reranking/fusion decision ("unjustified complexity until measured to help").

- [ ] **Phase 12: Falsifiable Measurement** — Per-instance dumps, McNemar-exact + paired bootstrap, `compare.py`, stratified dev/test split. May kill the current headline claim; that is its purpose.
- [ ] **Phase 13: Query/Document Asymmetry** — Apply BGE's query instruction prefix (currently a no-op), measure it in isolation on dev; add a bench-only embedding cache.
- [ ] **Phase 14: Single-Stage Sweep** — Tokenizer-accurate chunking, then chunk-size/stride, then rollup ablation; freeze one config on dev-200.
- [ ] **Phase 15: Cross-Encoder Reranking** — Pool-ceiling gate, then CPU cross-encoder reranker with stage-matched arms {bm25, dense, bm25+rerank, dense+rerank}.
- [ ] **Phase 16: LoCoMo Parity** — Dumps, prefix, rerank, per-category breakdown, structural full-coverage ceiling.
- [ ] **Phase 17: Final Evaluation & Reporting** — One held-out test-split run of the frozen config; `BENCHMARK_HANDOFF.md` updated with real significance numbers.

## Phase Details

### Phase 12: Falsifiable Measurement
**Goal**: The existing 0.866-vs-0.844 recall_all@5 lead becomes testable. Today both harnesses emit only aggregate means, so the gap is literally unfalsifiable. This phase adds per-instance dumps, exact paired-significance tests, and an unbiased stratified split — no retrieval config changes, no score changes. It may kill the current headline claim; that is its purpose.
**Depends on**: Phase 11 (v0.6.0 complete)
**Requirements**: STAT-01, STAT-02, STAT-03, SPLT-01, SPLT-02
**Success Criteria** (what must be TRUE):
  1. `bench/longmemeval.py --dump <path>` and `bench/locomo.py --dump <path>` each write one record per evaluated instance (`qid`, `question_type`/`category`, `gold`, `ranked`) at a depth controlled by `--dump-depth` (default 50), so pool-ceiling analysis at any R ≤ 50 is computable offline without re-running retrieval
  2. `bench/stats.py` exposes `mcnemar_exact(b, c)` (two-sided exact binomial on discordant pairs) and `paired_bootstrap(a, b, n_boot, seed)` (Δ + 95% CI); running either twice with the same seed produces identical output
  3. `bench/compare.py <dump_a> <dump_b>` prints the paired 2×2 table (a/b/c/d), Δ, McNemar-exact p, and the bootstrap CI on Δ; the table's cells sum to the number of shared instances
  4. `bench/_split.py::stratified_split(instances, dev_frac, seed)` partitions by `question_type` with a stable per-instance hash, and the dev/test question-type mix matches the full set
  5. Both harnesses accept `--split dev|test|all`; the head-slice `--limit` is no longer used to construct evaluation subsets, and `--split dev` is deterministic under a fixed seed
**Plans**: TBD

### Phase 13: Query/Document Asymmetry
**Goal**: BGE's query instruction prefix — currently a no-op because fastembed's `query_embed()` is a passthrough — is actually applied, and its effect is measured in isolation on dev using Phase 12's tooling. A bench-only embedding cache makes the sweeps in Phases 14-16 affordable by memoizing vectors across runs.
**Depends on**: Phase 12
**Requirements**: PFX-01, PFX-02, CACHE-01
**Success Criteria** (what must be TRUE):
  1. `bench/_retrieval.py::make_embedders(model)` returns distinct `(embed_docs, embed_query)` callables with a model-aware prefix registry (BGE query instruction; nomic `search_query:`/`search_document:`; e5 `query:`/`passage:`); `bench/grounding.py` is unmodified
  2. A test asserts the query string passed to `bm25_rank` is prefix-free, even when the semantic ranker's query prefix is active
  3. `bench/_embed_cache.py` memoizes embedding vectors keyed `sha256(model|kind|prefix|text)`; re-running the same dev-200 query returns identical vectors without recomputation (verified by an embedder call-count assertion), and no module under `flowstate/` imports it
  4. The prefix's effect on dev-200 `recall_all@5` is measured and reported via the Phase 12 dump/compare tooling (positive, negative, or ~0 — the number is reported, not assumed)
**Plans**: TBD

### Phase 14: Single-Stage Sweep
**Goal**: One frozen retrieval configuration is chosen on dev-200 before any test-split evaluation happens — tokenizer-accurate chunking first (closing the `chars = tokens * 4` heuristic gap that let a "400-token" chunk exceed the 512-token model window), then chunk-size/stride, then rollup strategy.
**Depends on**: Phase 13
**Requirements**: SWEEP-01, SWEEP-02, SWEEP-03
**Success Criteria** (what must be TRUE):
  1. `_chunk_text` sizes chunks by real token count; a test constructs a case where the old `chars = tokens * 4` heuristic would exceed a 512-token cap and confirms the fixed version does not
  2. `bench/longmemeval.py` accepts `--chunk-stride` alongside `--chunk-tokens`; a dev-200 sweep over chunk size {128, 256, 400, 512} then stride selects and records one frozen chunk configuration with its dev `recall_all@5`
  3. `semantic_rank_chunked` accepts `--rollup max|mean-top2|mean-top3`; the ablation is run with stride/overlap held at 0 and reports dev `recall_all@5` per rollup
  4. The single frozen configuration (chunk size, stride, rollup) selected in this phase is recorded and is the only configuration carried into Phases 15-17
**Plans**: TBD

### Phase 15: Cross-Encoder Reranking
**Goal**: The ranking headroom implied by `recall_any@5` = 0.966 vs `recall_all@5` = 0.866 (gold sessions are already retrieved, sitting at ranks 6-10) is captured by a CPU-feasible, production-viable cross-encoder — but only if a pool-ceiling gate justifies it, and never reported without its stage-matched baseline.
**Depends on**: Phase 14 (frozen config); the RERANK-01 gate reads Phase 12's dumps
**Requirements**: RERANK-01, RERANK-02, RERANK-03
**Success Criteria** (what must be TRUE):
  1. A pool-ceiling report computes `recall_all@R` for R ∈ {5, 10, 20, 50} per first-stage backend from the Phase 12 dumps, and states explicitly whether the ceiling at the chosen R justifies building the reranker (dense→rerank@10 caps at 0.946, BM25→rerank@10 caps at 0.904 — these are the numbers the gate must reconcile against)
  2. If the gate passes: `bench/_retrieval.py::rerank()` (backed by `fastembed.rerank.cross_encoder.TextCrossEncoder`, `Xenova/ms-marco-MiniLM-L-6-v2`) never raises and degrades to input order on failure — verified by a test that forces a failure
  3. Every reported reranked result ships with its stage-matched baseline: the arm set is {bm25, dense, bm25+rerank, dense+rerank} at identical R, k, and query handling in the same report — no reranked number appears alone
  4. If the gate fails (ceiling within noise of the current score), the phase's SUMMARY documents that finding instead of shipping an unjustified reranker
**Plans**: TBD

### Phase 16: LoCoMo Parity
**Goal**: LoCoMo gets the same measurement rigor as LongMemEval — dumps, query prefix, and reranking — plus a per-category breakdown that shows exactly where semantic currently loses to BM25 (measured: 0.459 vs 0.481 full-cov@5), read against the metric's structural ceiling rather than an implicit 1.0.
**Depends on**: Phase 13 (shares the prefix registry and embedding cache); reuses Phase 15's `rerank()`. LoCoMo docs are short and are never chunked, so this phase does not depend on Phase 14's sweep.
**Requirements**: LOCO-01, LOCO-02, LOCO-03
**Success Criteria** (what must be TRUE):
  1. `bench/locomo.py --dump` writes per-instance records, applies the Phase 13 query prefix, and invokes Phase 15's shared `rerank()` with no chunking
  2. Results are broken down per `category` (multi-hop, temporal, open-domain, single-hop, adversarial) using the same {bm25, dense, bm25+rerank, dense+rerank} arm set, showing exactly which categories the semantic arm loses on
  3. The harness reports the structural ceiling of `full_coverage@N` (the fraction of QA whose `|evidence| > N`, unachievable by construction) alongside the per-category breakdown in one output artifact
**Plans**: TBD

### Phase 17: Final Evaluation & Reporting
**Goal**: The dev-selected frozen configuration is run exactly once against the held-out test split, and `BENCHMARK_HANDOFF.md` is updated with the real, paired-significance answer to whether semantic retrieval beats BM25 — closing the milestone's core question honestly, whichever way it lands.
**Depends on**: Phase 15, Phase 16
**Requirements**: RPT-01
**Success Criteria** (what must be TRUE):
  1. The frozen dev-selected configuration (chunking, prefix, rollup, rerank-or-not per RERANK-01's gate outcome) is run exactly once on `--split test`, with no re-selection based on the test result
  2. `bench/BENCHMARK_HANDOFF.md` §2 and §5 report McNemar-exact p and the bootstrap Δ CI for the headline dense-vs-BM25 comparison on the test split
  3. The existing full-500 number is explicitly labeled dev-selected, distinct from the one-shot test-split confirmatory number
  4. Resolved Tier-1/Tier-2 backlog items in §5 are struck through; items still open remain unstruck
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Land the v2 Pivot | v0.3.0 | direct | Complete | 2026-05-25 (b38bbd6) |
| 2. Operate Safely | v0.3.0 | 4/4 | Complete | 2026-05-25 |
| 3. Ingredients — Pack, Canon, Fixtures | v0.4.0 | 3/3 | Complete | 2026-06-06 |
| 4. Integration — Layered CAG Assembly | v0.4.0 | 1/1 | Complete | 2026-06-06 |
| 5. UX — Guided Kickoff + Hygiene | v0.4.0 | 2/2 | Complete | 2026-06-06 |
| 6. Run Journal | v0.5.0 | 3/3 | Complete | 2026-06-08 |
| 7. Gotchas Accumulator | v0.5.0 | 4/4 | Complete | 2026-06-08 |
| 8. Runnable Verification | v0.5.0 | 3/3 | Complete | 2026-06-09 |
| 9. Embedding Provider + Vector Store Foundation | v0.6.0 | 2/2 | Complete | 2026-06-18 |
| 10. Semantic Memory Retrieval | v0.6.0 | 1/1 | Complete | 2026-06-18 |
| 11. Semantic Wiki Retrieval | v0.6.0 | 1/1 | Complete | 2026-06-18 |
| 12. Falsifiable Measurement | v0.7.0 | 0/? | Not started | - |
| 13. Query/Document Asymmetry | v0.7.0 | 0/? | Not started | - |
| 14. Single-Stage Sweep | v0.7.0 | 0/? | Not started | - |
| 15. Cross-Encoder Reranking | v0.7.0 | 0/? | Not started | - |
| 16. LoCoMo Parity | v0.7.0 | 0/? | Not started | - |
| 17. Final Evaluation & Reporting | v0.7.0 | 0/? | Not started | - |

## Backlog

Items deferred from completed milestones. Promote via `/gsd-review-backlog`.

- **WIKI-F1** (deferred at v0.6.0 close) — No production caller passes `include_layers={"wiki"}`, so the semantic wiki retrieval mechanism built in Phase 11 never fires in practice. Needs a curated `.planning/codebase/wiki/` corpus plus orchestrator wiring. The mechanism is implemented, tested, and dormant. **Promoted into [`SEED-001`](./seeds/SEED-001-harness-tax-and-value.md) Phase 20** — this is FlowState's only context layer with a proven lift (0.825 ≈ oracle 0.800) and it is switched off, while the layer that does fire (pack) measured ≈ none.
- **SEED-001 — v0.8.0 "Harness Tax & Value"** ([seed](./seeds/SEED-001-harness-tax-and-value.md)) — Proposed 4-phase milestone (18–21): measure token/latency cost (none exists today; `prefix_tokens` is a `len()//4` estimate), enforce evaluator independence, **activate the wiki**, then run the paired-design verdict on a real repo using the already-built `--layers`/`--paired` rig. Surfaces automatically at the next `/gsd-new-milestone`. Answers the harness-value question that v0.7.0 (retrieval-only) deliberately does not. See `bench/BENCHMARKING_SCOPE.md`.
- **RERANK-F1** (v0.7.0 Future Requirement) — Wiring a reranker into FlowState's production `MemoryStore.get_context()` path. v0.7.0 measures it on the bench first; production wiring only if RERANK-03 shows the embeddings (not merely the reranker) carry the win.
- **RERANK-F2** (v0.7.0 Future Requirement) — `BAAI/bge-reranker-base`/`bge-reranker-large`. ~1.5-2.5 hr/run on CPU, beyond the production-viability bar; at most a single confirmatory run, and only with a GPU.
- **RET-F1** (v0.7.0 Future Requirement) — Long-context unchunked embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q`, 8192 tok) as a capacity-vs-chunking ablation. Informative, not expected to move the headline.
- **RET-F2** (v0.7.0 Future Requirement) — Turn-level retrieval with a `turn2session` rollup (LongMemEval ships `evaluate_retrieval_turn2session`) as an alternative to chunking.
- **RET-F3** (v0.7.0 Future Requirement) — Query-side work: feeding `question_date` into temporal-reasoning queries; HyDE / query expansion.
- **QA-F1..F4** (v0.7.0 Future Requirements) — The entire QA track (revert/gate `_READER_INSTRUCTION`, official per-question-type judge prompts, `char_budget` truncation check, running `locomo_qa.py` on real data). v0.7.0 is retrieval-only; QA fixes address a separate, already-known regression.
