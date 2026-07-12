# Roadmap: FlowState

## Milestones

- ✅ **v0.3.0 v2 Pivot + Operate-Safely** — Phases 1-2 (shipped 2026-06-06)
- ✅ **v0.4.0 Context Compaction & Compounding** — Phases 3-5 (shipped 2026-06-06)
- ✅ **v0.5.0 Compounding Loop** — Phases 6-8 (shipped 2026-06-09)
- ✅ **v0.6.0 Semantic Retrieval** — Phases 9-11 (shipped 2026-07-10)
- ✅ **v0.6.1 Make the Names Real** — Phases 12-15, 15 plans (shipped 2026-07-11) — [archive](./milestones/v0.6.1-ROADMAP.md)
- ✅ **v0.6.2 Make the Harness Real** — eval harness runs E2E and fails loud (SEED-002; phases 16-18, shipped 2026-07-11) — [archive](./milestones/v0.6.2-ROADMAP.md)
- 🚧 **v0.8.0 Harness Tax & Value** — measure the tax, activate the wiki, decouple the evaluator (SEED-001; phases 19-22). Phases 19-21 shipped; **Phase 22 (The Verdict) PAUSED — 5×3 paid benchmark run owed.**
- 🚧 **v0.9.0 Sandbox Guardrail** — OS-level blast-radius boundary on every agent subprocess (SEED-003; phases 23-25). Scoped in parallel with the owed v0.8.0 verdict run; shares no files with `bench/`.
- 📋 **v0.7.0 Retrieval Benchmark Rigor** — deferred to Backlog; the deterministic retrieval track, does not gate v0.8.0 (spec: `deferred/v0.7.0-REQUIREMENTS.md`)

## Phases

- [x] **Phase 19: The Tax** - Real token/cost/latency accounting through `BridgeResult`, `RunSnapshot`, and `bench/report.py` — completed 2026-07-11
- [x] **Phase 20: Evaluator Independence** - Judge-model ≠ producer-model enforced in code, with multi-judge averaging — completed 2026-07-11
- [x] **Phase 21: Activate the Wiki** - Promote the memory→wiki distiller to production and fire the dormant semantic wiki layer — completed 2026-07-11
- [ ] **Phase 22: The Verdict** - Pre-registered, paired-design run on a real repo measuring quality and tax per context-layer arm — ⏸ PAUSED (code shipped; 5×3 paid run owed)
- [x] **Phase 23: Linux Parity + Core Seam** - `flowstate/sandbox.py` seam + observe/denylist + macOS SBPL & Linux bwrap+landlock builders shipped (SBX-02); Linux spike **PARITY PROVEN** (SBX-01) — completed 2026-07-12
- [ ] **Phase 24: Thread the Seam + Config** - Route the agent-directed subprocess sites through `wrap()` (auth preserved), add the defaulted `ProjectPreferences.sandbox` field (no migration); env-scrub live by default, confinement opt-in (SBX-03, SBX-04)
- [ ] **Phase 25: Confinement + Verification** - Ship the allow-default+selective-deny macOS SBPL + bwrap Linux profiles behind `confine`; E2E-prove a real `claude --print` succeeds confined while writes outside `project_root` and `~/.ssh` reads are denied; fail loud on a missing sandbox binary (SBX-05, SBX-06)

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

<details>
<summary>✅ v0.6.2 Make the Harness Real (Phases 16-18) — SHIPPED 2026-07-11</summary>

Eval harness runs E2E and fails loud (SEED-002; plumbing/correctness only — measurement science and production wiring stay v0.8.0). All 5 requirements (HAR-01..05) complete.

- [x] Phase 16: Mode-Honest Reporting (1/1 plan) — real mode never leaks the cheap-mode caveat; reports state mode/arm/sample-size/producers (HAR-01)
- [x] Phase 17: No Silent No-Op Arms + Producers Wired E2E (3/3 plans) — memory→wiki distiller writes the article corpus the Phase-11 reader globs; fail-loud producer gate; one prepare-fixture path (HAR-02, HAR-03)
- [x] Phase 18: Close the Loop with a CI, E2E (3/3 plans) — seeded paired-bootstrap CI helper; one command prior-runs→distill→inject→judge→CI; CI-safe E2E smoke over every arm (HAR-04, HAR-05)

Full detail: [`milestones/v0.6.2-ROADMAP.md`](./milestones/v0.6.2-ROADMAP.md).

</details>

## Phase Details

### Phase 19: The Tax

**Goal**: Every pipeline run can be measured for what it actually costs (tokens, cost, latency) instead of estimated — the accounting layer the harness has been missing since `bench/` began.
**Depends on**: v0.6.2 complete (nothing new this phase touches is unbuilt: `RunSnapshot`, `bench/report.py`, `output_format="json"` all already exist)
**Requirements**: TAX-01, TAX-02, TAX-03, TAX-04
**Success Criteria** (what must be TRUE):

  1. `BridgeResult` carries a real `usage` field (tokens_in/out/cache_read) populated via the existing `output_format="json"` path, and every existing caller's `.output` is unchanged (no regression).
  2. `RunSnapshot` records real `tokens_in` / `tokens_out` / `cache_read` / `wall_clock_s` per run, replacing the `len(prefix)//4` `prefix_tokens` estimate as the source of truth.
  3. `bench/report.py` shows per-arm tokens and seconds alongside the existing quality metrics, visibly excluded from `compounding_score` (Track-2, not Track-1).
  4. The report's cost-per-success line names `flowstate verify`'s deterministic acceptance gates — not "commits" — as its denominator.

**Plans**: 3 plans

- [x] 19-01-PLAN.md — TAX-01: BridgeResult.usage + duration_s via the json path (text-mode byte-identical) + cumulative bridge totals
- [x] 19-02-PLAN.md — TAX-02: real tokens/wall_clock_s on RunSnapshot threaded bridge→journal→capture; compute_scorecard unchanged
- [x] 19-03-PLAN.md — TAX-03/04: per-arm tokens+seconds in report.py (Track-2, excluded) + cost per verified acceptance gate

### Phase 20: Evaluator Independence

**Goal**: The judge can no longer silently grade its own producer's output, and a single judge call becomes a defensible multi-judge verdict — without disturbing `metrics.py`'s authority.
**Depends on**: Phase 19 (shares the report surface the tax lands on)
**Requirements**: IND-01, IND-02, IND-03
**Success Criteria** (what must be TRUE):

  1. Running `bench/judge.py` with `--judge-model` absent, or equal to the producer model, fails loud (explicit error / nonzero exit) instead of silently grading.
  2. `judge.py` supports multi-judge averaging (majority vote + Wilson CI), mirroring the `--judge-models` pattern already shipped in `bench/grounding.py`.
  3. A test asserts `bench/metrics.py`'s `compounding_score` stays the authoritative deterministic scorer and the LLM judge remains excluded under the new multi-judge path.

**Plans**: 2 plans

- [x] 20-01-PLAN.md — IND-01/IND-02: independence guard helper + `python -m bench.judge` CLI + multi-judge aggregation (0-10 mean/median + Wilson-CI pass-rate) in judge.py
- [x] 20-02-PLAN.md — IND-01/IND-03: wire the shared guard into compound_eval.py/close_loop.py + exclusion test proving compounding_score stays deterministic and judge-excluded

### Phase 21: Activate the Wiki

**Goal**: The proven-best context layer (distilled wiki + semantic retrieval, measured 0.825 ≈ oracle 0.800) stops sitting dormant and actually fires on production runs, with the default path staying byte-identical when the flag is off.
**Depends on**: v0.6.2's shipped `bench/distiller.py` (the producer already exists; this phase is production wiring only)
**Requirements**: WIKI-03, WIKI-04, WIKI-05, WIKI-06
**Success Criteria** (what must be TRUE):

  1. A production entry point runs the memory→wiki distiller end-of-run, writing a manifest-tracked, staleness-gated `.planning/codebase/wiki/` article corpus (mirrors the `flowstate pack` pattern) that regenerates only when memory changed, so the *next* run reads this run's distilled knowledge.
  2. An opt-in config flag makes the orchestrator pass `include_layers={"wiki"}` to `build_context_prefix()`; with the flag off, the output is byte-identical to today's default.
  3. With the flag on but the `[semantic]` extra absent, the wiki layer degrades to a no-op-with-warning — never a hard crash — and `pip install flowstate[semantic]` is surfaced as the requirement for the KNN path.
  4. A dogfood smoke-test runs FlowState's own pipeline on a FlowState task with the wiki flag on, against this project's real `memory.db`, and asserts the corpus is globbed and top-k articles are injected with the run green (acceptance = "the layer fires," not "quality improved").

**Plans**: 3 plans

- [x] 21-01-PLAN.md — WIKI-03: promote bench/distiller.py → flowstate/distiller.py (bench re-imports) + `flowstate distill` CLI + kind="wiki" manifest & is_wiki_stale (staleness mirrors flowstate pack); run_pipeline distill side untouched (D-03 fence)
- [x] 21-02-PLAN.md — WIKI-04/WIKI-05: opt-in `wiki_layer` pref (default false, byte-identical off) + _STANDARD_LAYERS ∪ {wiki} union at orchestrator.py:254 + one-time `[semantic]`-absent degradation warning
- [x] 21-03-PLAN.md — WIKI-06: dogfood integration test — distill this project's real memory.db, build prefix with the wiki union, assert the layer fires (globbed + top-k injected), skip/static-degrade gracefully

### Phase 22: The Verdict

**Goal**: A pre-registered, paired-design measurement honestly answers whether FlowState's context stack — and specifically the now-active wiki layer — earns its token/latency tax on a real repo, accepting a null result as a legitimate outcome.
**Depends on**: Phase 19 (tax accounting), Phase 20 (independent judge), Phase 21 (wiki actually fires) — this is the capstone phase; it needs all three measurement primitives in place before it can produce a trustworthy verdict.
**Requirements**: VERD-01, VERD-02, VERD-03
**Success Criteria** (what must be TRUE):

  1. Verdict rules — effect-size threshold, CI width, minimum n, what counts as a win — are written down and committed *before* the paired-design run starts.
  2. A paired-design run via `bench/close_loop.py` executes on a real repo (not `bench/fixtures/sample_project`) across arms `none`/`pack`/`memory`/`wiki`/`full`, and the report shows the compounding curve across run 1→N (run 1 empty memory → no wiki; wiki value, if any, appears run 2+).
  3. The final report states quality **and** tax per arm, applies the pre-registered rules, and a null `wiki − none` (or any arm) is accepted and documented as a valid outcome that licenses stripping the layer — not retried until significant.

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 22-01-PLAN.md — Pre-register the verdict protocol (VERD-01): commit 22-PREREGISTRATION.md before any real run
- [ ] 22-02-PLAN.md — Build bench/verdict.py: 4-contrast driver + Holm-Bonferroni + quality/tax/compounding report, proven in --mode cheap (VERD-02/03)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 22-03-PLAN.md — Gated paid --mode real run on floxybot2 + write 22-VERDICT.md applying the pre-registered rules (VERD-02/03)

**Note**: expensive — live LLM runs across 5 arms × multiple trials × multiple runs (compounding curve); smoke at reduced trials/runs before scaling per the SEED's cost-reality note.

### Phase 23: Linux Parity + Core Seam

**Goal**: The Linux confinement unknown is retired (bwrap+landlock either preserves `claude` auth under an allow-default profile, mirroring the passed macOS Seatbelt spike, or the gap is honestly documented), and `flowstate/sandbox.py` exists with the single `wrap(cmd, surface, project_root, env)` seam and a non-blocking `observe` tier — the foundation every later phase threads through.
**Depends on**: SEED-003 (macOS Seatbelt spike already passed; sandflox is the reference design). Nothing upstream is unbuilt.
**Requirements**: SBX-01, SBX-02
**Success Criteria** (what must be TRUE):

  1. A Linux `bwrap`+landlock spike demonstrates an allow-default + selective-deny profile that preserves `claude` auth and API reachability (mirroring the macOS finding), OR the parity gap is documented with its consequence for phases 24–25 — a failed spike is a recorded outcome, not a silent skip.
  2. `flowstate/sandbox.py` exposes `wrap(cmd, surface, project_root, env)` with per-platform profile builders; the default `observe` tier is env-scrub only and never blocks a command (unit-tested against a fake command; profile emission golden-tested).

**Plans:** 4 plans in 3 waves

- [x] 23-01-PLAN.md — Core seam + observe tier + env-scrub with the _AUTH_EXEMPT carve-out (SBX-02) [wave 1]
- [x] 23-02-PLAN.md — macOS SBPL profile builder + Linux bwrap mount-namespace arg builder (SBX-02) [wave 2]
- [x] 23-03-PLAN.md — Linux Landlock ctypes + functional bwrap smoke test + D-03 degradation ladder (SBX-02) [wave 3]
- [x] 23-04-PLAN.md — Linux bwrap+landlock spike + committed 23-SPIKE-LINUX.md finding (SBX-01) [wave 1]

### Phase 24: Thread the Seam + Config

**Goal**: The agent-directed subprocess sites actually run through `wrap()` with auth intact, and a user can choose their posture via a defaulted `ProjectPreferences.sandbox` field — env-scrub live by default, confinement opt-in — with no state migration.
**Depends on**: Phase 23 (the `wrap()` seam and `observe` tier must exist before anything routes through them).
**Requirements**: SBX-03, SBX-04
**Success Criteria** (what must be TRUE):

  1. The agent-directed subprocess sites are routed through `wrap()` — at minimum `bridge.py:308` (the auth-load-bearing `claude --print` call) — and Keychain/API reachability is preserved on every wrapped call; internal git-read (`discipline.py`) and npm (`gsd_vendor.py`) sites are wrapped or left bare per an explicit, documented plan-time decision.
  2. `ProjectPreferences` gains a defaulted `sandbox` level field (`observe` / `confine`); load stays backward-compatible with no state migration, and the default is `observe`.

### Phase 25: Confinement + Verification

**Goal**: The `confine` tier is real and proven — a live `claude --print` succeeds inside the kernel sandbox while writes outside the project root and reads of `~/.ssh` are denied, on both macOS and Linux — and a missing sandbox binary fails loud instead of silently running unconfined.
**Depends on**: Phase 23 (profile builders) and Phase 24 (the seam + config field the `confine` level toggles).
**Requirements**: SBX-05, SBX-06
**Success Criteria** (what must be TRUE):

  1. The `confine` tier ships the allow-default + selective-deny macOS SBPL profile and the Linux bwrap equivalent; an end-to-end test confirms a real `claude --print` succeeds confined (auth survives, API reachable) while a write outside `project_root` and a read of `~/.ssh` are denied.
  2. Under `confine`, a missing platform sandbox binary (`sandbox-exec` / `bwrap`) fails loud with an install hint — the guardrail never silently runs a command unconfined when confinement was requested.

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
| 18. Close the Loop with a CI | v0.6.2 | 3/3 | Complete   | 2026-07-11 |
| 19. The Tax | v0.8.0 | 3/3 | Complete    | 2026-07-11 |
| 20. Evaluator Independence | v0.8.0 | 2/2 | Complete    | 2026-07-11 |
| 21. Activate the Wiki | v0.8.0 | 3/3 | Complete    | 2026-07-11 |
| 22. The Verdict | v0.8.0 | 1/3 | In Progress|  |
| _v0.7.0 Retrieval Benchmark Rigor_ | v0.7.0 | deferred | renumbers 16-21 on start | - |

## Backlog

Items deferred from completed milestones. Promote via `/gsd-review-backlog`.

- **v0.7.0 Retrieval Benchmark Rigor** (deferred behind v0.6.1, 2026-07-10) — Fully scoped: 6 phases, 18 requirements, spec at `.planning/deferred/v0.7.0-REQUIREMENTS.md`. Pushed back so the adapter stubs (v0.6.1) are fixed first — no further harness benchmarking until the enforcement layer can fail. Resumes via `/gsd-new-milestone` after v0.6.1 ships; renumbers to phases 16-21 (v0.6.1 grew to 4 phases with GSD bundling).
- **WIKI-F1** (deferred at v0.6.0 close) — No production caller passes `include_layers={"wiki"}`, so the semantic wiki retrieval mechanism built in Phase 11 never fires in practice. Needs a curated `.planning/codebase/wiki/` corpus plus orchestrator wiring. The mechanism is implemented, tested, and dormant. **Promoted into [`SEED-001`](./seeds/SEED-001-harness-tax-and-value.md) → v0.8.0 Phase 21** — this is FlowState's only context layer with a proven lift (0.825 ≈ oracle 0.800) and it is switched off, while the layer that does fire (pack) measured ≈ none.
- **SEED-001 — v0.8.0 "Harness Tax & Value"** ([seed](./seeds/SEED-001-harness-tax-and-value.md)) — ROADMAPPED this session as phases 19-22 (see Phase Details above): measure token/latency cost (none exists today; `prefix_tokens` is a `len()//4` estimate), enforce evaluator independence, **activate the wiki**, then run the paired-design verdict on a real repo using the already-built `--layers`/`--paired` rig. Answers the harness-value question that v0.7.0 (retrieval-only) deliberately does not. See `bench/BENCHMARKING_SCOPE.md`.
- **RERANK-F1** (v0.7.0 Future Requirement) — Wiring a reranker into FlowState's production `MemoryStore.get_context()` path. v0.7.0 measures it on the bench first; production wiring only if RERANK-03 shows the embeddings (not merely the reranker) carry the win.
- **RERANK-F2** (v0.7.0 Future Requirement) — `BAAI/bge-reranker-base`/`bge-reranker-large`. ~1.5-2.5 hr/run on CPU, beyond the production-viability bar; at most a single confirmatory run, and only with a GPU.
- **RET-F1** (v0.7.0 Future Requirement) — Long-context unchunked embedders (`jina-embeddings-v2-base-en`, `nomic-embed-text-v1.5-Q`, 8192 tok) as a capacity-vs-chunking ablation. Informative, not expected to move the headline.
- **RET-F2** (v0.7.0 Future Requirement) — Turn-level retrieval with a `turn2session` rollup (LongMemEval ships `evaluate_retrieval_turn2session`) as an alternative to chunking.
- **RET-F3** (v0.7.0 Future Requirement) — Query-side work: feeding `question_date` into temporal-reasoning queries; HyDE / query expansion.
- **QA-F1..F4** (v0.7.0 Future Requirements) — The entire QA track (revert/gate `_READER_INSTRUCTION`, official per-question-type judge prompts, `char_budget` truncation check, running `locomo_qa.py` on real data). v0.7.0 is retrieval-only; QA fixes address a separate, already-known regression.
- **Auto-distill at end of every run** (v0.8.0 Future Requirement, from `REQUIREMENTS.md`) — WIKI-03 ships explicit-first (production caller invoked deliberately); auto-once-proven is a follow-up once Phase 22's verdict justifies the invisible loop.
