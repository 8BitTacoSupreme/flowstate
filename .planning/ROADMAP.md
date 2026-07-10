# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- ✅ **v0.5.0 Compounding Loop** — Phases 6-8 (shipped 2026-06-09)
- ✅ **v0.6.0 Semantic Retrieval** — Phases 9-11 (shipped 2026-07-10)
- 🚧 **v0.6.1 Make the Names Real** — Phases 12-15 (in progress)
- 📋 **v0.6.2 Make the Harness Real** — the eval harness runs E2E and fails loud; **gates all further benchmarking** (SEED-002; phases 16-18 after v0.6.1)
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

### 🚧 v0.6.1 Make the Names Real (In Progress)

**Milestone Goal:** Undead the adapter stubs before benchmarking. FlowState's `research`/`strategy`/`discipline` adapters are named after real MIT upstreams (Karpathy Autoresearch, Garry Tan Gstack, Jesse Vincent Superpowers) but implement almost none of them — and the enforcement stage is structurally incapable of failing. Make the pipeline honest, make each adapter do its namesake's mechanism in-process, and vendor the two MIT skill sets so `flowstate launch` surfaces them with zero user install.

- [ ] **Phase 12: Honesty & Failure-Capability** — Stop the pipeline reporting broken runs as clean. Discipline can fail; research/strategy surface failure; a live run with no `claude` CLI fails loud instead of writing stub text as artifacts.
- [ ] **Phase 13: Adapters Earn Their Names** — In-process mechanisms: research measure→keep/discard over output; strategy scored rubric + verdict; discipline runs tests + reads real git state + checks hook contents.
- [ ] **Phase 14: Vendor & Surface** — Vendor gstack + superpowers MIT SKILL.md into `flowstate/skills/`, auto-install to `.claude/skills/`, surface via `flowstate launch strategy|discipline`; NOTICE + README fixes.
- [ ] **Phase 15: Bundle GSD** — Vendor the pinned MIT GSD full runtime (skills + `get-shit-done/` + `gsd-sdk`) into `flowstate/vendor/gsd/`; install unconditionally (no detect, no prompt); documented refresh path. **Reverses "no cross-harness packaging."**

## Phase Details

### Phase 12: Honesty & Failure-Capability
**Goal**: A broken run must fail, not report "completed." Today `discipline.py:56` hardcodes `success=True`, `orchestrator.py:315-319` never reads the audit result, `research.py:113-122` returns `success=True` with "*Research failed*" in the artifact, and a live run with no `claude` CLI writes `[dry-run]` stub text as real output. This phase makes failure representable and surfaced — foundation for Phase 13 (an adapter can't report a mechanism running until it can report it failing).
**Depends on**: Phase 11 (v0.6.0 complete)
**Requirements**: HON-01, HON-02, HON-03, HON-04, HON-05, HON-06
**Success Criteria** (what must be TRUE):
  1. A repo missing the required-set (no git, no test config) makes `discipline.check_setup().success` return `False` (previously impossible — it was hardcoded `True`)
  2. The orchestrator marks the Discipline step `BLOCKED` on a failed audit and `_print_summary` reflects it; `flowstate discipline` exits non-zero on failure and zero on a clean repo
  3. `research.py::execute()` returns `ToolResult(success=False)` when all topics fail; no artifact contains "*Research failed*" text alongside a success result
  4. A live run with `FLOWSTATE_CLAUDE_BIN` pointing at a missing binary marks steps `BLOCKED` and writes no `[dry-run] claude prompt` text into `report.md`/`strategy.md`
  5. `gsd_adapter.py`'s "optional LLM enrichment" docstring matches the code (claim removed or implemented)
**Plans**: 3 plans
- [x] 12-01-PLAN.md — Discipline can fail (required-set) + orchestrator routing via _run_step + `flowstate discipline` CLI (HON-01, HON-02)
- [x] 12-02-PLAN.md — research/strategy surface failure + gsd_adapter docstring reconciled (HON-03, HON-04, HON-06)
- [x] 12-03-PLAN.md — live run with no `claude` CLI fails loud (remove silent dry-run swap) (HON-05)

### Phase 13: Adapters Earn Their Names
**Goal**: Each adapter performs the core mechanism its namesake is built on, in pure Python + `claude --print`, with no new runtime deps and no prompt self-modification.
**Depends on**: Phase 12 (failure must be representable first)
**Requirements**: MECH-01, MECH-02, MECH-03
**Success Criteria** (what must be TRUE):
  1. The research adapter scores each topic section for groundedness against the fixture's `retrieval_questions` and retries-or-discards a weak section within a bounded budget, recording kept vs discarded — Autoresearch's measure→keep/discard over output, never over prompts
  2. The strategy adapter emits parseable per-dimension scores (0–10) and a verdict (ship/pivot/kill); an unparseable rubric is a failure (via HON-04) — Gstack's scored-review pattern
  3. The discipline adapter runs the project's tests (captures pass/fail), reads real git state (dirty/branch/ahead-behind), and checks hook contents (non-empty/executable) — Superpowers' RED-GREEN gate; the result feeds HON-01's required-set
  4. All three mechanisms are covered by offline tests (injected bridge / temp git repo / subprocess stub) and the `--dry-run` MOCK paths are unchanged
**Plans**: 3 plans
- [x] 13-01-PLAN.md — MECH-01: research groundedness measure→keep/discard over output
- [x] 13-02-PLAN.md — MECH-02: strategy scored rubric + ship/pivot/kill verdict
- [x] 13-03-PLAN.md — MECH-03: discipline runs tests + real git state + hook contents

### Phase 14: Vendor & Surface
**Goal**: The two MIT skill sets ship inside FlowState and install themselves, so `flowstate launch` surfaces the real upstream tools with zero manual user install — self-contained from this repo.
**Depends on**: Phase 12 (honest launch/detect surface)
**Requirements**: VEND-01, VEND-02, VEND-03, VEND-04, VEND-05
**Success Criteria** (what must be TRUE):
  1. `flowstate/skills/gstack/` and `flowstate/skills/superpowers/` contain the vendored MIT `SKILL.md` assets, and `NOTICE` carries both MIT attributions (© Garry Tan, © Jesse Vincent)
  2. `flowstate install-skills` (and `init`/`kickoff`) copies the vendored skills into the project's `.claude/skills/`; a fresh project needs no manual skill install
  3. `flowstate launch strategy` prints the `claude` + `/office-hours` handoff and `flowstate launch discipline` prints the superpowers TDD-skill handoff when the vendored skills are installed
  4. README shows the real current test count (985, not 803/947) and the Superpowers URL is `obra/superpowers` (not the 404 `obra/claude-code-superpowers`)
**Plans**: 4 plans
- [x] 14-01-PLAN.md — Vendor gstack + superpowers MIT SKILL.md trees + LICENSE + NOTICE (VEND-01, VEND-02)
- [x] 14-02-PLAN.md — README reconciliation: URL, doctor count, sqlite-vec wording, adapter acknowledgments (VEND-05)
- [x] 14-03-PLAN.md — `flowstate install-skills` installer + init/kickoff auto-invoke (VEND-03)
- [x] 14-04-PLAN.md — `flowstate launch strategy|discipline` skill handoffs (VEND-04)

### Phase 15: Bundle GSD
**Goal**: GSD ships inside FlowState and installs itself — the user never installs GSD separately, and FlowState never detects or prompts for it. Reverses the "no cross-harness packaging" decision per user direction (2026-07-10): *"It should be there, by whatever legal means."* GSD (`gsd-build/get-shit-done`) is MIT (© Lex Christopherson), so the path is legal with attribution.
**Depends on**: Phase 14 (extends the `flowstate install-skills` installer)
**Requirements**: GSD-01, GSD-02, GSD-03, GSD-04, GSD-05
**Success Criteria** (what must be TRUE):
  1. `flowstate/vendor/gsd/` contains a pinned GSD distribution (skills + `get-shit-done/` Node runtime + `gsd-sdk`) with the upstream MIT `LICENSE` captured verbatim and a recorded `VERSION`/commit; `NOTICE` carries the GSD attribution
  2. `flowstate install-skills` (and `init`/`kickoff`) installs GSD unconditionally into `.claude/skills/` + `.claude/get-shit-done/` and makes `gsd-sdk` invokable — no detect gate, no prompt
  3. In a fresh project with no separately-installed GSD, `flowstate launch gsd <N>` produces a working handoff against the vendored GSD (the launcher's GSD detect-and-suggest path is neutralized)
  4. A documented refresh path (mirroring `flowstate pack` staleness/manifest) updates the pinned GSD snapshot deliberately; the vendored VERSION is inspectable
**Plans**: 5 plans
- [x] 15-01-PLAN.md — Vendor the pinned MIT GSD distribution + LICENSE/VERSION/NOTICE + coverage/collection exclusions (GSD-01)
- [x] 15-02-PLAN.md — Extend the installer to lay down GSD unconditionally into .claude/skills + .claude/get-shit-done + invokable gsd-sdk (GSD-02)
- [ ] 15-03-PLAN.md — Neutralize the launcher GSD detect-and-suggest path so launch gsd is unconditional (GSD-03)
- [ ] 15-04-PLAN.md — Documented GSD refresh/staleness path mirroring flowstate pack + inspectable VERSION (GSD-04)
- [ ] 15-05-PLAN.md — README reconciliation to the bundled-and-auto-installed reality + true test count (GSD-05)

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
| 15. Bundle GSD | v0.6.1 | 2/5 | In Progress|  |
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
