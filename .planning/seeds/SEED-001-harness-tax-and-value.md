---
id: SEED-001
status: dormant
planted: 2026-07-10
planted_during: v0.7.0 Retrieval Benchmark Rigor (pre-Phase-12)
trigger_when: starting a milestone that touches harness value, context-layer attribution, token/cost accounting, evaluator independence, or the dormant wiki layer (WIKI-F1)
scope: 4 phases (18-21), ~1 milestone
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
   measured **≈ none**. Yet no `flowstate/` module passes `include_layers={"wiki"}` (deferred
   WIKI-F1), and **neither `.planning/codebase/wiki.md` nor `.planning/codebase/wiki/` exists
   on disk**. Worse, `bench/wikigen.py` writes the single-file `wiki.md` while the Phase-11
   semantic retriever reads the **article directory** (`flowstate/context_prefix.py:54,64`) —
   the generator does not produce what the retriever reads. The layer that works never fires;
   the layer that fires measured neutral.

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

Surface after v0.7.0 Phase 17 completes. v0.7.0 is the deterministic *retrieval* track and
must not be derailed; this is the *harness-value* track.

**Prerequisite (added 2026-07-10):** v0.6.2 "Make the Harness Real" ([[SEED-002]]) must land
first — it builds the bench-side plumbing this milestone assumes (mode-honest reporting, no
silent no-op arms, the memory→wiki distiller + article-corpus producer, and multi-sample CIs
wired into `compound_eval`). With v0.6.2 shipped, this milestone's Phase 19/20 shrink to the
*production* half: enforce judge-model ≠ producer-model, add the production wiki caller +
manifest/staleness, and the tax accounting — the bench-side halves are already real.

## Scope Estimate

**4 phases (18–21), ~14 requirements.** Continuing numbering from v0.7.0's Phase 17.

- **Phase 18 — The Tax (TAX-01..04).** `BridgeResult.usage` + `duration_s`; use the existing
  dead `output_format="json"` path while keeping `.output` byte-identical; real
  `tokens_in/out/cache_read` + `wall_clock_s` in `RunSnapshot`; per-arm tokens/seconds in
  `bench/report.py`. Denominator for cost-per-success is `flowstate verify`'s deterministic
  acceptance gates (`flowstate/verify.py:57-129`) — **not** "commits"; the pipeline produces
  artifacts, not commits, and naming the denominator honestly matters more than matching the
  reviewer's phrasing. Deterministic, no LLM.
- **Phase 19 — Evaluator independence (IND-01..03).** Fail loud when `--judge-model` is absent
  or equals the producer model. Multi-judge averaging in `judge.py` (the runbook's item #3,
  the only prerequisite never built) — copy the pattern already in `bench/grounding.py`
  (`--judge-models` default `"sonnet,sonnet,opus"` at `:1136`, majority vote + `_wilson`).
  Assert with a test that `metrics.py` stays authoritative and the judge stays excluded.
- **Phase 20 — Activate the wiki (WIKI-03..06).** *The headline.* Article-corpus generator
  producing what the retriever actually reads; an opt-in production caller so the Phase-11
  semantic wiki layer finally fires; manifest-tracked + staleness-gated like `flowstate pack`;
  byte-identical default when wiki is off.
- **Phase 21 — The verdict (VERD-01..03).** Pre-register verdict rules *before* running.
  Paired design on a **real repo** (not `bench/fixtures/sample_project`, which sits near a
  ~6/10 ceiling). Arms `none` · `pack` · `memory` · `wiki` · `full` using the already-built
  `--layers` × `--paired` × `replicate.py` rig. Report quality **and** tax per arm.

**Statistics:** reuse `bench/stats.py::paired_bootstrap` from v0.7.0 Phase 12. Cohen's d over
5–10 trials is noisy and already produced one false positive; report a paired-bootstrap CI on
the within-trial normalized improvement instead.

**Cost reality:** the runbook's 4 arms × 10 trials × 8 runs = 320 live pipeline runs ≈ 1.5–2
days wall-clock and large $. Smoke at `--trials 2 --runs 3` per arm first; scope to 3–4 arms
at N=6/K=6 and expand only if signal appears.

## Breadcrumbs

Already built — reuse, do not rebuild:

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
- single-file wiki generator — `bench/wikigen.py`

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
