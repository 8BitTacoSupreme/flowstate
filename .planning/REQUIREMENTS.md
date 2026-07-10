# Requirements: FlowState — v0.7.0 Retrieval Benchmark Rigor

**Defined:** 2026-07-10
**Core Value:** Each run starts smarter than the last. v0.6.0 replaced lexical retrieval with semantic KNN on the strength of one wiki bench; v0.7.0 establishes whether that choice actually beats BM25 on public benchmarks — with a paired significance test, stage-matched baselines, and no selection bias.

## Milestone v0.7.0 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase.

### Significance Infrastructure (STAT)

- [ ] **STAT-01**: `bench/longmemeval.py` and `bench/locomo.py` accept `--dump <path>` and write one record per evaluated instance (`qid`, `question_type`/`category`, `gold`, `ranked`), with ranked depth controlled by `--dump-depth` (default 50) so pool-ceiling analysis at any R ≤ 50 is computable offline without re-running retrieval.
- [ ] **STAT-02**: A `bench/stats.py` module provides `mcnemar_exact(b, c)` (two-sided exact binomial on discordant pairs) and `paired_bootstrap(a, b, n_boot, seed)` returning Δ plus a 95% CI; both are deterministic under a fixed seed.
- [ ] **STAT-03**: A `bench/compare.py` CLI takes two dump files and prints the paired 2×2 table (a/b/c/d), Δ, McNemar-exact p, and the bootstrap CI on Δ; the table's cells sum to the number of shared instances.

### Evaluation Splits (SPLT)

- [ ] **SPLT-01**: A `bench/_split.py` module provides `stratified_split(instances, dev_frac, seed)` that partitions instances by `question_type` with a stable per-instance hash, so the dev and test sets carry the same question-type mix as the full set.
- [ ] **SPLT-02**: Both retrieval harnesses accept `--split dev|test|all`; the head-slice `--limit` is documented as biased (LongMemEval-S is type-blocked) and is no longer used to construct evaluation subsets.

### Query/Document Asymmetry (PFX)

- [ ] **PFX-01**: `bench/_retrieval.py` exposes `make_embedders(model) -> (embed_docs, embed_query)` with a model-aware prefix registry (BGE query instruction; nomic `search_query:`/`search_document:`; e5 `query:`/`passage:`), leaving `bench/grounding.py` unmodified.
- [ ] **PFX-02**: The query prefix is applied only inside the semantic ranker and never reaches `bm25_rank`, whose disjunctive OR query would otherwise be polluted by the prefix's tokens; a test asserts the query string BM25 receives is prefix-free.

### Embedding Cache (CACHE)

- [ ] **CACHE-01**: A `bench/_embed_cache.py` sqlite cache keyed `sha256(model | kind | prefix | text)` memoizes embedding vectors across bench runs, so rollup ablations, reranker sweeps, and reruns do not re-embed; it is bench-only and never used by `flowstate/`.

### Retrieval Sweep (SWEEP)

- [ ] **SWEEP-01**: `_chunk_text` sizes chunks by real token count rather than the `chars = tokens * 4` heuristic, so a "400-token" chunk cannot silently exceed a 512-token model window.
- [ ] **SWEEP-02**: `bench/longmemeval.py` accepts `--chunk-stride` (overlap) alongside `--chunk-tokens`, and a dev-only sweep over chunk size {128, 256, 400, 512} then stride selects one frozen configuration.
- [ ] **SWEEP-03**: `semantic_rank_chunked` accepts `--rollup max|mean-top2|mean-top3`; the ablation is run with overlap held at 0 (overlap changes chunk count and therefore every rollup's length statistics).

### Reranking (RERANK)

- [ ] **RERANK-01**: A pool-ceiling report computes `recall_all@R` for R ∈ {5, 10, 20, 50} per first stage from the STAT-01 dumps; it gates the reranker (if the ceiling at the chosen R is within noise of the current score, no reranker is built).
- [ ] **RERANK-02**: `bench/_retrieval.py` exposes a `rerank()` backed by `fastembed.rerank.cross_encoder.TextCrossEncoder`, restricted to CPU-feasible production-viable models (`Xenova/ms-marco-MiniLM-L-6-v2`), never raising and degrading to the input order on any failure.
- [ ] **RERANK-03**: Every reported reranked result ships with its stage-matched baseline: the arm set is {bm25, dense, bm25+rerank, dense+rerank} at identical R, k, and query handling, so "dense beats BM25" is licensed only by the dense-vs-bm25 pair.

### LoCoMo Parity (LOCO)

- [ ] **LOCO-01**: `bench/locomo.py` gains `--dump`, the query prefix, and the shared `rerank()` (no chunking — LoCoMo docs are short), with the same stage-matched arm set.
- [ ] **LOCO-02**: LoCoMo results are broken down per `category` (multi-hop, temporal, open-domain, single-hop, adversarial), showing where the semantic arm loses to BM25.
- [ ] **LOCO-03**: The harness reports the structural ceiling of `full_coverage@N` — the fraction of QA whose `|evidence| > N`, for which full coverage is unachievable by construction — so the metric is not read as understating every arm equally.

### Reporting (RPT)

- [ ] **RPT-01**: The frozen dev-selected configuration is run once on the held-out test split; `bench/BENCHMARK_HANDOFF.md` §2/§5 is updated with McNemar-exact p, the bootstrap Δ CI, the full-500 number labelled as dev-selected, and the resolved backlog items struck.

## Future Requirements

Acknowledged, deferred — not in this milestone's roadmap.

### Reranking

- **RERANK-F1**: Wiring a reranker into FlowState's production `MemoryStore.get_context()` path — v0.7 measures it on the bench first; production wiring only if RERANK-03 shows the embeddings (not merely the reranker) carry the win.
- **RERANK-F2**: `BAAI/bge-reranker-base` / `bge-reranker-large` — ~1.5–2.5 hr/run on CPU and beyond the production-viability bar; a single confirmatory run at most, and only with a GPU.

### Retrieval

- **RET-F1**: Long-context unchunked embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q`, 8192 tok) as an ablation testing capacity-vs-chunking as competing fixes for the truncation bug — informative for the story, not expected to move the headline.
- **RET-F2**: Turn-level retrieval with a `turn2session` rollup (LongMemEval ships `evaluate_retrieval_turn2session`) as an alternative to chunking.
- **RET-F3**: Query-side work — feeding `question_date` into temporal-reasoning queries; HyDE / query expansion.

### QA Track

- **QA-F1**: Reverting or gating `_READER_INSTRUCTION`, the measured QA regression that is still the default reader prompt. Note: selecting a reader prompt by max oracle accuracy is itself tuning-on-test; the clean move is adopting the paper's official reader prompt, not reverting to the higher-scoring one.
- **QA-F2**: Adopting LongMemEval's official per-question-type GPT-4o judge prompts in place of the single binary `_factcheck`.
- **QA-F3**: Verifying `char_budget=48000` does not truncate gold sessions in the QA oracle arm.
- **QA-F4**: Running `bench/locomo_qa.py` on real data (string-F1, no judge → cheap; never yet run).

## Out of Scope

| Feature | Reason |
|---------|--------|
| The entire QA track (reader prompt, judge prompts, `char_budget`) | v0.7.0 is retrieval-only. QA fixes address an *understated* number, which is a different problem from the *unproven* retrieval claim this milestone exists to settle. Deferred as QA-F1..F4. |
| Hybrid BM25+dense RRF fusion as a shipped path | Permitted as an explicitly-labelled **bench-only** arm, never as FlowState's production retrieval — v0.6.0 deliberately rejected lexical fusion (a Critical review catch: an FTS5 gate would suppress the lexically-disjoint case semantic retrieval exists to serve). |
| `bge-large` / Stella-V5 embedders | CPU-only machine; 1.2GB+ models make a sweep infeasible. Report what we can actually run. |
| Modifying `bench/grounding.py` | ADD-ONLY constraint, declared in `bench/longmemeval.py`'s module docstring. The query/document interface change lands in `bench/_retrieval.py` instead. |
| New runtime dependencies | The installed fastembed 0.8 already ships cross-encoders and 8192-token embedders. Nothing new is required, and the dep-free-default core install is untouched (bench extras only). |
| Tuning the judge, cherry-picking `--seed`, or dropping hard question types | `bench/BENCHMARK_HANDOFF.md` §6 integrity rules. A better number obtained this way is not a result. |
| Committing benchmark datasets | LoCoMo is CC BY-NC (do not redistribute); LongMemEval-S is 265MB. `data/` is gitignored; re-fetch per handoff §7. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| STAT-01 | Phase 12 | Pending |
| STAT-02 | Phase 12 | Pending |
| STAT-03 | Phase 12 | Pending |
| SPLT-01 | Phase 12 | Pending |
| SPLT-02 | Phase 12 | Pending |
| PFX-01 | Phase 13 | Pending |
| PFX-02 | Phase 13 | Pending |
| CACHE-01 | Phase 13 | Pending |
| SWEEP-01 | Phase 14 | Pending |
| SWEEP-02 | Phase 14 | Pending |
| SWEEP-03 | Phase 14 | Pending |
| RERANK-01 | Phase 15 | Pending |
| RERANK-02 | Phase 15 | Pending |
| RERANK-03 | Phase 15 | Pending |
| LOCO-01 | Phase 16 | Pending |
| LOCO-02 | Phase 16 | Pending |
| LOCO-03 | Phase 16 | Pending |
| RPT-01 | Phase 17 | Pending |

**Coverage:**
- Milestone requirements: 18 total
- Mapped to phases: 18 (populated by roadmapper)
- Unmapped: 0

---
*Requirements defined: 2026-07-10*
