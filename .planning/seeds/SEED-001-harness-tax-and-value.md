---
id: SEED-001
status: dormant
planted: 2026-07-10
planted_during: v0.7.0 Retrieval Benchmark Rigor (pre-Phase-12)
trigger_when: starting a milestone that touches harness value, context-layer attribution, token/cost accounting, evaluator independence, or the dormant wiki layer (WIKI-F1)
scope: 4 phases (19-22), ~1 milestone
refined: 2026-07-11 (post-v0.6.2 — bench-side wiki producer now SHIPPED; Phase 20 shrinks to production wiring + dogfood-first acceptance; renumbered 19-22 since v0.6.2 consumed phases 16-18)
---

# SEED-001: v0.8.0 "Harness Tax & Value" — measure the cost, activate the wiki, decouple the evaluator

Proposed milestone. Answers the question v0.7.0 deliberately does not: **does FlowState's
context stack improve output quality enough to justify its token and latency cost?**

## Why This Matters

External review argued FlowState should be benched against vanilla/naive-RAG baselines
rather than BM25, and should measure "the Tax" (tokens + latency per successful run).
The BM25 half of that is wrong — see `bench/BENCHMARKING_SCOPE.md` (BM25 is the *incumbent*
implementation v0.6.0 replaced inside `MemoryStore.get_context()`, and `recall_all@k` is the
only evaluator in the stack with zero LLM in the loop). But the scope claim is right:
**retrieval quality ≠ harness value**, and Track 2 is only half-built.

Three findings make this milestone worth running:

1. **The Tax is unmeasured.** No token, cost, or latency accounting exists anywhere in
   `bench/`. `prefix_tokens` (`bench/metrics.py:51`, `bench/capture.py:186`) is
   `len(prefix) // 4` — an *input-context estimate*, not consumption. `ClaudeBridge.run()`
   already accepts `output_format="json"` (`flowstate/bridge.py:197,230`) and its docstring
   already cites `usage.cache_read_input_tokens` (`:16`) — but **no caller ever passes it**
   and `BridgeResult` has no `usage` field (`:105-109`). The data is one flag away and is
   currently discarded.

2. **The proven-best context layer is switched off.** Distilled wiki + semantic retrieval
   measured **0.825 ≈ oracle 0.800** (right article 17/20 vs BM25's 3/20). Raw code pack
   measured **≈ none**. The generator/reader mismatch is now **fixed bench-side** (v0.6.2
   Phase 17): `bench/distiller.py` distills `memory.db` → the **article corpus** in
   `.planning/codebase/wiki/` — the exact directory `_semantic_wiki_layer` globs
   (`flowstate/context_prefix.py:64`). (`bench/wikigen.py`'s single-file `wiki.md` at `:54`
   only feeds the *degraded static fallback*, not the KNN path — so the semantic wiki is a
   distillation of accumulated project **memory**, not codebase architecture, despite the
   `codebase/wiki` path name.) The one remaining gap is **production wiring**: no `flowstate/`
   module passes `include_layers={"wiki"}` (`orchestrator.py:254` calls `build_context_prefix`
   with none), and nothing in production runs the distiller to populate the corpus. The layer
   that works still never fires; the layer that fires (pack) measured neutral.

3. **Evaluator independence is unenforced.** `bench/judge.py` shells out to `claude` to grade
   artifacts that `flowstate.bridge` produced via `claude`. Nothing requires
   judge-model ≠ producer-model. (The authoritative `CompoundingScore` in `bench/metrics.py`
   *is* deterministic and LLM-free, and the judge is explicitly excluded at
   `bench/report.py:80` — so this is a guard-rail gap, not a live contamination.)

And the honest baseline: **the harness-value experiment already ran and came back null**
(Cohen's d 0.29; the d=0.62 was a run-0 noise artifact, and the control arm ended *higher*
in absolute quality). If `wiki − none` is also null on a real repo, layers become removal
candidates. That is a legitimate outcome.

## When to Surface

**Trigger:** starting a milestone that touches any of —

- token / cost / latency accounting, or "is the harness worth it" questions
- context-layer attribution (`pack − none`, `memory − none`, `wiki − none`, `full − pack`)
- the dormant wiki layer / WIKI-F1 / `.planning/codebase/wiki/` corpus generation
- LLM-judge reliability or evaluator independence
- any external claim that FlowState's benchmarks measure the wrong thing

This is the *harness-value* track; the deterministic *retrieval* track (v0.7.0 Retrieval
Benchmark Rigor) is deferred in the ROADMAP Backlog and does not gate this milestone.

**Prerequisite (SATISFIED 2026-07-11):** v0.6.2 "Make the Harness Real" ([[SEED-002]]) has
**shipped** (phases 16–18: mode-honest reporting, no silent no-op arms, the memory→wiki
distiller + article-corpus producer, and multi-sample paired-bootstrap CIs wired into
`bench/close_loop.py`). Consequently this milestone's wiki phase (now Phase 21) shrinks to the
**production** half — promote the distiller into the pipeline, add the opt-in production reader
call + manifest/staleness, and the tax accounting; the bench-side halves are already real and
covered by tests.

## Scope Estimate

**4 phases (19–22), ~14 requirements.** Renumbered post-v0.6.2 (which consumed phases 16–18).

- **Phase 19 — The Tax (TAX-01..04).** `BridgeResult.usage` + `duration_s`; use the existing
  dead `output_format="json"` path while keeping `.output` byte-identical; real
  `tokens_in/out/cache_read` + `wall_clock_s` in `RunSnapshot`; per-arm tokens/seconds in
  `bench/report.py`. Denominator for cost-per-success is `flowstate verify`'s deterministic
  acceptance gates (`flowstate/verify.py:57-129`) — **not** "commits"; the pipeline produces
  artifacts, not commits, and naming the denominator honestly matters more than matching the
  reviewer's phrasing. Deterministic, no LLM.
- **Phase 20 — Evaluator independence (IND-01..03).** Fail loud when `--judge-model` is absent
  or equals the producer model. Multi-judge averaging in `judge.py` (the runbook's item #3,
  the only prerequisite never built) — copy the pattern already in `bench/grounding.py`
  (`--judge-models` default `"sonnet,sonnet,opus"` at `:1136`, majority vote + `_wilson`).
  Assert with a test that `metrics.py` stays authoritative and the judge stays excluded.
- **Phase 21 — Activate the wiki (WIKI-03..06).** *The headline.* The bench-side producer is
  already shipped (Phase 17 `bench/distiller.py`); this phase is **production wiring only**:
  - **WIKI-03 Producer in production** — promote/call the memory→wiki distiller from the
    pipeline (end-of-run, so the *next* run reads this run's distilled knowledge), writing
    `.planning/codebase/wiki/`. Manifest-tracked + staleness-gated by mirroring the
    `flowstate pack` pattern (breadcrumb below), so it regenerates only when memory changed.
  - **WIKI-04 Reader opt-in** — a config flag (e.g. `wiki_layer: true`); when set, the
    `orchestrator.py:254` `build_context_prefix(...)` call passes `include_layers={..., "wiki"}`.
    **Byte-identical default when off** (the whole reason the layer is opt-in — a Phase-10/11
    invariant; do not regress it). Degrades gracefully when the `[semantic]` extra is absent
    (static single-file read → empty), so core install stays dep-free.
  - **WIKI-05 Semantic extra UX** — surface `pip install flowstate[semantic]` (fastembed) as
    the requirement for the KNN path; the flag is a no-op-with-warning without it.
  - **WIKI-06 Dogfood smoke-test (phase acceptance)** — run FlowState's own pipeline on a
    FlowState task with the wiki flag on, using *this* project's already-rich `memory.db`;
    assert the wiki layer actually fires (corpus globbed, top-k injected) and the run stays
    green. This proves the wiring E2E and sidesteps cold-start **before** any paid multi-run
    verdict. Acceptance = "the layer demonstrably fires on a real FlowState run," NOT "quality
    improved" (that is Phase 22's job).
- **Phase 22 — The verdict (VERD-01..03).** Pre-register verdict rules *before* running.
  Paired design on a **real repo** (not `bench/fixtures/sample_project`, ~6/10 ceiling), driven
  by the v0.6.2 **`bench/close_loop.py`** command (prior-runs→distill→inject→judge→CI) across
  arms `none` · `pack` · `memory` · `wiki` · `full`. Crucially this must measure the
  **compounding curve, not a one-shot**: run 1 has empty memory → no wiki; the wiki's value (if
  any) appears run 2+ as distilled prior-run knowledge is retrieved. Report quality **and** tax
  per arm. A null `wiki − none` is a legitimate outcome (strip the layer).

**Statistics:** reuse the **shipped** `bench/bootstrap.py::paired_bootstrap_ci` (seeded,
stdlib; v0.6.2 Phase 18) wired through `bench/close_loop.py` — trial-index-paired with
None-hole handling (`_per_trial_improvements`) and contract-strict trial reads (quick task
260710-x5a). Cohen's d over 5–10 trials is noisy and already produced one false positive;
report the paired-bootstrap CI on the within-trial normalized improvement instead. (The
original SEED note pointed at `bench/stats.py` from the deferred v0.7.0 Phase 12 — that never
shipped; the v0.6.2 modules above are the real ones.)

**Cost reality:** the runbook's 4 arms × 10 trials × 8 runs = 320 live pipeline runs ≈ 1.5–2
days wall-clock and large $. Smoke at `--trials 2 --runs 3` per arm first; scope to 3–4 arms
at N=6/K=6 and expand only if signal appears.

## Breadcrumbs

Already built — reuse, do not rebuild:

Shipped in v0.6.2 (the bench-side halves this milestone assumed were still TODO):
- **memory→wiki distiller (the article-corpus producer)** — `bench/distiller.py::main` writes
  `.planning/codebase/wiki/*.md` from `memory.db`; this is WIKI-03's core logic to promote to production.
- **one-command loop** — `bench/close_loop.py` (prior-runs→distill→inject→judge→CI); drives Phase 22's verdict.
- **paired-bootstrap CI** — `bench/bootstrap.py::paired_bootstrap_ci` (seeded, stdlib).
- **one prepare-fixture path** — `bench/prepare_fixture.py` (pack + wiki producers per arm).
- **fail-loud arm gate** — `bench/compound_eval.py::_missing_producer` / `_EXIT_PRODUCER_ABSENT`.
- **production reader call site (the wiring target)** — `flowstate/orchestrator.py:254`
  `build_context_prefix(root, memory, _pk_query, console=console)` — WIKI-04 adds `include_layers`.

Older breadcrumbs (still valid):
- `_LAYERS_MAP` — `bench/compound_eval.py:60-66` (arms `full|none|pack|memory|wiki`)
- `_run_one()` include_layers monkeypatch — `bench/compound_eval.py:169-179`
- `_paired_normalize()` — `bench/replicate.py:60-67`; `--layers` nargs at `:100-106`
- `_wilson`, `_factcheck`, `--judge-models` — `bench/grounding.py:267,327,1136`
- `CompoundingScore` 4-axis deterministic scorer — `bench/metrics.py` (stdlib-only imports)
- judge-excluded note — `bench/report.py:80`
- `output_format="json"` dead path — `flowstate/bridge.py:197,230`; `BridgeResult` at `:105-109`
- acceptance gates — `flowstate/verify.py:57-129`
- `flowstate pack` staleness/manifest pattern — mirror it for the wiki
- wiki path constants — `flowstate/context_prefix.py:54` (`wiki.md`), `:64` (article dir)
- single-file wiki generator (pack→`wiki.md`; feeds only the DEGRADED static fallback, NOT the KNN corpus) — `bench/wikigen.py`

Context docs: `bench/BENCHMARKING_SCOPE.md` (two-track model), `bench/PAIRED_DESIGN_RUNBOOK.md`
(protocol + landed-status), `bench/BENCHMARK_HANDOFF.md` (Track-1 results).

## Notes

Captured 2026-07-10 after an external review prompted a scope audit. The review's architecture
diagram (Superpowers / GStack / autoresearch) described layers that do not exist — those are
dead v0.1.0 tool aliases (`flowstate/state.py:63-65`) deleted on migration. See the dead-alias
table in `bench/BENCHMARKING_SCOPE.md`. The review's *scope* claim survived scrutiny; its
architecture claim did not.

**Integrity rules for this milestone:** never let the LLM judge become the load-bearing metric;
judge-model ≠ producer-model enforced in code, not convention; verdict rules pre-registered
before the run; report the tax even when it is embarrassing — the point of measuring cost is to
be able to strip a layer. A null result is a result.
