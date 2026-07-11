# Requirements: v0.8.0 Harness Tax & Value

**Goal:** Now that the eval harness is trustworthy (v0.6.2), answer the question v0.7.0 deliberately doesn't — **does FlowState's context stack improve output quality enough to justify its token and latency cost?** Measure the tax, decouple the evaluator, activate the dormant wiki layer in production, then run a pre-registered paired-design verdict on a real repo. Source: [`seeds/SEED-001-harness-tax-and-value.md`](./seeds/SEED-001-harness-tax-and-value.md). The bench-side halves shipped in v0.6.2; this milestone is the production + measurement-science half.

**Integrity rules (milestone-wide):** never let the LLM judge become the load-bearing metric (`metrics.py` stays authoritative, judge excluded from `compounding_score`); judge-model ≠ producer-model enforced in code, not convention; verdict rules pre-registered before the run; report the tax even when it's embarrassing; a null result is a result.

## v0.8.0 Requirements

### The Tax (token/cost/latency accounting)

- [x] **TAX-01**: `ClaudeBridge.run()` captures real usage — `BridgeResult` gains a `usage` field populated via the existing `output_format="json"` path, while `.output` stays byte-identical (no caller regression). Deterministic, no new LLM calls.
- [x] **TAX-02**: `RunSnapshot` records real `tokens_in` / `tokens_out` / `cache_read` + `wall_clock_s` per run (replacing the `len(prefix)//4` `prefix_tokens` estimate as the source of truth for consumption).
- [x] **TAX-03**: `bench/report.py` reports per-arm tokens and seconds alongside the existing quality metrics (Track-2, excluded from `compounding_score`).
- [x] **TAX-04**: cost-per-success uses `flowstate verify`'s deterministic acceptance gates as the denominator (not "commits"); the denominator is named honestly in the report.

### Evaluator Independence

- [ ] **IND-01**: `bench/judge.py` fails loud when `--judge-model` is absent or equals the producer model — no silent same-model grading.
- [ ] **IND-02**: multi-judge averaging in `judge.py` (majority vote + Wilson CI), mirroring the pattern already in `bench/grounding.py` (`--judge-models`).
- [ ] **IND-03**: a test asserts `bench/metrics.py` stays the authoritative deterministic scorer and the LLM judge remains excluded from `compounding_score` under the new multi-judge path.

### Activate the Wiki (production wiring of the dormant WIKI-F1 layer)

- [ ] **WIKI-03**: a production caller runs the memory→wiki distiller (promoted from `bench/distiller.py`) to write the `.planning/codebase/wiki/` article corpus, manifest-tracked and staleness-gated like `flowstate pack` (regenerates only when memory changed); runs end-of-run so the next run reads this run's distilled knowledge.
- [ ] **WIKI-04**: an opt-in config flag makes the orchestrator pass `include_layers={"wiki"}` to `build_context_prefix()`, so the Phase-11 semantic wiki layer fires in production; the default (flag off) stays byte-identical, and the path degrades gracefully when the `[semantic]` extra is absent.
- [ ] **WIKI-05**: the `flowstate[semantic]` extra is surfaced as the requirement for the KNN wiki path; with the flag on but the extra absent, the layer is a no-op-with-warning (never a hard crash).
- [ ] **WIKI-06**: a dogfood smoke-test runs FlowState's own pipeline on a FlowState task with the wiki flag on, using this project's `memory.db`, and asserts the wiki layer demonstrably fires (corpus globbed, top-k injected) with the run green — phase acceptance is "the layer fires," NOT "quality improved."

### The Verdict

- [ ] **VERD-01**: verdict rules (effect-size threshold, CI width, minimum n, what counts as a win) are pre-registered in writing **before** the paired-design run.
- [ ] **VERD-02**: a paired-design run via `bench/close_loop.py` on a **real repo** (not `bench/fixtures/sample_project`) across arms `none` · `pack` · `memory` · `wiki` · `full`, measuring the **compounding curve** (run 1 empty → wiki value appears run 2+), not a one-shot.
- [ ] **VERD-03**: the verdict reports quality **and** tax per arm and applies the pre-registered rules; a null `wiki − none` (or any arm) is an accepted, documented outcome that licenses stripping the layer.

## Future Requirements (deferred)

- **RERANK-F1 / RERANK-F2**: production reranker wiring (from v0.7.0 backlog) — only if the bench shows the embeddings, not merely the reranker, carry the win.
- **RET-F1..F3 / QA-F1..F4**: v0.7.0 retrieval/QA-track future requirements — see `.planning/deferred/v0.7.0-REQUIREMENTS.md`.
- **Auto-distill at end of every run** (vs explicit `flowstate distill`) — WIKI-03 ships explicit-first; auto-once-proven is a follow-up once the verdict justifies the invisible loop.

## Out of Scope

- **v0.7.0 Retrieval Benchmark Rigor** — the deterministic retrieval track; deferred to the ROADMAP Backlog and does not gate this milestone.
- **BM25-vs-vanilla-RAG re-baselining** — the external review's framing; BM25 is the incumbent v0.6.0 replaced, already the counterfactual (`bench/BENCHMARKING_SCOPE.md`).
- **Curated hand-authored wiki articles** — the wiki corpus is *generated* by the distiller from memory; hand-authoring bypasses the compounding architecture WIKI-03 exists to prove.
- **New runtime dependencies in the core install** — the semantic path stays behind the optional `[semantic]` extra; default install stays dep-free.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TAX-01 | Phase 19 | Complete |
| TAX-02 | Phase 19 | Complete |
| TAX-03 | Phase 19 | Complete |
| TAX-04 | Phase 19 | Complete |
| IND-01 | Phase 20 | Pending |
| IND-02 | Phase 20 | Pending |
| IND-03 | Phase 20 | Pending |
| WIKI-03 | Phase 21 | Pending |
| WIKI-04 | Phase 21 | Pending |
| WIKI-05 | Phase 21 | Pending |
| WIKI-06 | Phase 21 | Pending |
| VERD-01 | Phase 22 | Pending |
| VERD-02 | Phase 22 | Pending |
| VERD-03 | Phase 22 | Pending |
