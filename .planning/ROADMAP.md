# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- ✅ **v0.5.0 Compounding Loop** — Phases 6-8 (shipped 2026-06-09)
- ✅ **v0.6.0 Semantic Retrieval** — Phases 9-11 (shipped 2026-07-10)
- ✅ **v0.6.1 Make the Names Real** — Phases 12-15, 15 plans (shipped 2026-07-11) — [archive](./milestones/v0.6.1-ROADMAP.md)
- 🚧 **v0.6.2 Make the Harness Real** — the eval harness runs E2E and fails loud; **gates all further benchmarking** (SEED-002; phases 16-18, in progress)
- 📋 **v0.7.0 Retrieval Benchmark Rigor** — deferred behind v0.6.1 → v0.6.2; renumbers after v0.6.2 (spec: `deferred/v0.7.0-REQUIREMENTS.md`)
- 📋 **v0.8.0 Harness Tax & Value** — SEED-001; follows v0.7.0

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

### ✅ v0.6.1 Make the Names Real (Shipped 2026-07-11)

Phases 12–15 (15 plans) — adapters made honest and real (12–13), the two MIT skill sets + GSD bundled and self-installing (14–15). Full detail: [`milestones/v0.6.1-ROADMAP.md`](./milestones/v0.6.1-ROADMAP.md).

## Phase Details

### 🚧 v0.6.2 Make the Harness Real (In Progress)

**Milestone Goal:** Make the eval harness itself run end-to-end and **fail loud** before any further benchmarking. Plumbing/correctness only — no measurement science, verdicts, or production wiring (those stay v0.8.0 / SEED-001). Hard gate on v0.7.0 + v0.8.0. Full scope: [`seeds/SEED-002-harness-e2e.md`](./seeds/SEED-002-harness-e2e.md).

### Phase 16: Mode-Honest Reporting
**Goal**: `bench/compound_eval.py` `--mode real` never emits the cheap-mode caveat; the report header, `mode_note`, and caveat reflect the actual mode; every report states mode, arm, sample size (K/trials), and which producer artifacts were present. Deterministic, no LLM.
**Depends on**: v0.6.1 complete
**Requirements**: HAR-01
**Success Criteria** (what must be TRUE):
  1. A `--mode real` run's report/output contains NO cheap-mode caveat string; a regression test asserts this.
  2. Every report states mode (cheap|real), arm, sample size (K/trials), and which producer artifacts were present.
**Plans**: 1 plan
- [x] 16-01-PLAN.md — thread mode/arm/sample-size/producers into the report; real mode never leaks the cheap-mode caveat (HAR-01)

### Phase 17: No Silent No-Op Arms + Producers Wired E2E
**Goal**: Every arm whose producer artifact is absent fails loud (never a bare number), and the bench-side producers the readers actually consume are shipped — the memory→wiki distiller (promoted from the spike) and the article corpus the Phase-11 semantic retriever reads. One `prepare-fixture` path.
**Depends on**: Phase 16
**Requirements**: HAR-02, HAR-03
**Success Criteria** (what must be TRUE):
  1. The `wiki`/`pack` arms fail loud (or emit "arm measured nothing: producer X absent") when their producer artifact is missing — never a bare number.
  2. `bench/` ships a memory→wiki distiller (promoted from `scratchpad/distill_spike.py`) and produces the article corpus the Phase-11 retriever reads (closes SEED-001 #2 bench-side).
  3. One `prepare-fixture` path generates what each arm needs before the arm matrix runs.
**Plans**: 3 plans (2 waves)
- [x] 17-01-PLAN.md — bench/distiller.py: memory→wiki distiller writing the article corpus the Phase-11 reader globs (HAR-03a/b)
- [x] 17-02-PLAN.md — fail-loud gate in compound_eval.py: absent producer → "arm measured nothing" marker + non-zero exit (HAR-02)
- [x] 17-03-PLAN.md — bench/prepare_fixture.py: one path wiring run_pack + distiller per arm (HAR-03 criterion 3)

### Phase 18: Close the Loop with a CI, E2E
**Goal**: Multi-sample judging + paired-bootstrap CI wired into `compound_eval`'s Track-2 path (reusing `grounding.py`/`replicate.py`); one command runs prior-runs→distill→inject→judge and returns a CI'd delta; a green E2E smoke test exercises every arm's plumbing and asserts fail-loud on a missing producer.
**Depends on**: Phase 17
**Requirements**: HAR-04, HAR-05
**Success Criteria** (what must be TRUE):
  1. `compound_eval` Track-2 emits a paired-bootstrap CI'd delta from multi-sample judging (not a single-shot score), reusing existing machinery.
  2. One command runs prior-runs→distill→inject→judge on a fixture end-to-end with a CI'd result.
  3. A green, CI-safe E2E smoke test exercises every arm's plumbing and asserts the harness fails loud on a missing producer.
**Plans**: 3 plans (2 waves)
- [x] 18-01-PLAN.md — bench/bootstrap.py seeded paired-bootstrap CI helper + wire the CI'd delta into replicate.py/report.py Track-2 output (HAR-04)
- [ ] 18-02-PLAN.md — bench/close_loop.py: the one command running prior-runs→distill→inject→judge→CI, with a CI-safe cheap mode (HAR-04)
- [x] 18-03-PLAN.md — tests/test_bench_e2e_smoke.py: CI-safe E2E smoke exercising every arm's plumbing + asserting fail-loud exit 3 (HAR-05)

<details>
<summary>📋 v0.7.0 Retrieval Benchmark Rigor (deferred behind v0.6.1 — renumbers to 16-21 on start)</summary>

Scoped and roadmapped this session, then deferred so the adapter stubs get fixed first (a harness whose enforcement layer cannot fail can't be meaningfully benchmarked). The full 6-phase plan, success criteria, and 18 requirements are preserved at `.planning/deferred/v0.7.0-REQUIREMENTS.md`. When v0.6.1 ships, `/gsd-new-milestone` for v0.7.0 will continue numbering from v0.6.1's last phase (→ phases 15-20). Headline facts (verified): `recall_any@5` = 0.966 for both arms; the 0.866-vs-0.844 lead is untestable until per-instance dumps land; LongMemEval-S is type-blocked so `--limit` is biased. See `bench/BENCHMARK_HANDOFF.md` and STATE.md's deferred-facts block.

</details>

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
| 12. Honesty & Failure-Capability | v0.6.1 | 3/3 | Complete   | 2026-07-10 |
| 13. Adapters Earn Their Names | v0.6.1 | 3/3 | Complete    | 2026-07-10 |
| 14. Vendor & Surface | v0.6.1 | 4/4 | Complete    | 2026-07-10 |
| 15. Bundle GSD | v0.6.1 | 5/5 | Complete    | 2026-07-11 |
| 16. Mode-Honest Reporting | v0.6.2 | 1/1 | Complete    | 2026-07-11 |
| 17. No Silent No-Op Arms + Producers | v0.6.2 | 3/3 | Complete   | 2026-07-11 |
| 18. Close the Loop with a CI | v0.6.2 | 2/3 | In Progress|  |
| _v0.7.0 Retrieval Benchmark Rigor_ | v0.7.0 | deferred | renumbers 16-21 on start | - |

## Backlog

Items deferred from completed milestones. Promote via `/gsd-review-backlog`.

- **v0.7.0 Retrieval Benchmark Rigor** (deferred behind v0.6.1, 2026-07-10) — Fully scoped: 6 phases, 18 requirements, spec at `.planning/deferred/v0.7.0-REQUIREMENTS.md`. Pushed back so the adapter stubs (v0.6.1) are fixed first — no further harness benchmarking until the enforcement layer can fail. Resumes via `/gsd-new-milestone` after v0.6.1 ships; renumbers to phases 16-21 (v0.6.1 grew to 4 phases with GSD bundling).
- **WIKI-F1** (deferred at v0.6.0 close) — No production caller passes `include_layers={"wiki"}`, so the semantic wiki retrieval mechanism built in Phase 11 never fires in practice. Needs a curated `.planning/codebase/wiki/` corpus plus orchestrator wiring. The mechanism is implemented, tested, and dormant. **Promoted into [`SEED-001`](./seeds/SEED-001-harness-tax-and-value.md) Phase 20** — this is FlowState's only context layer with a proven lift (0.825 ≈ oracle 0.800) and it is switched off, while the layer that does fire (pack) measured ≈ none.
- **SEED-001 — v0.8.0 "Harness Tax & Value"** ([seed](./seeds/SEED-001-harness-tax-and-value.md)) — Proposed 4-phase milestone (18–21): measure token/latency cost (none exists today; `prefix_tokens` is a `len()//4` estimate), enforce evaluator independence, **activate the wiki**, then run the paired-design verdict on a real repo using the already-built `--layers`/`--paired` rig. Surfaces automatically at the next `/gsd-new-milestone`. Answers the harness-value question that v0.7.0 (retrieval-only) deliberately does not. See `bench/BENCHMARKING_SCOPE.md`.
- **RERANK-F1** (v0.7.0 Future Requirement) — Wiring a reranker into FlowState's production `MemoryStore.get_context()` path. v0.7.0 measures it on the bench first; production wiring only if RERANK-03 shows the embeddings (not merely the reranker) carry the win.
- **RERANK-F2** (v0.7.0 Future Requirement) — `BAAI/bge-reranker-base`/`bge-reranker-large`. ~1.5-2.5 hr/run on CPU, beyond the production-viability bar; at most a single confirmatory run, and only with a GPU.
- **RET-F1** (v0.7.0 Future Requirement) — Long-context unchunked embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q`, 8192 tok) as a capacity-vs-chunking ablation. Informative, not expected to move the headline.
- **RET-F2** (v0.7.0 Future Requirement) — Turn-level retrieval with a `turn2session` rollup (LongMemEval ships `evaluate_retrieval_turn2session`) as an alternative to chunking.
- **RET-F3** (v0.7.0 Future Requirement) — Query-side work: feeding `question_date` into temporal-reasoning queries; HyDE / query expansion.
- **QA-F1..F4** (v0.7.0 Future Requirements) — The entire QA track (revert/gate `_READER_INSTRUCTION`, official per-question-type judge prompts, `char_budget` truncation check, running `locomo_qa.py` on real data). v0.7.0 is retrieval-only; QA fixes address a separate, already-known regression.
