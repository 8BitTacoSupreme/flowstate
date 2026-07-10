---
id: SEED-002
status: active
planted: 2026-07-10
planted_during: v0.6.1 Make the Names Real (post-Phase-13)
committed_as: v0.6.2 Make the Harness Real
trigger_when: before running ANY further benchmark (v0.7.0 Retrieval Benchmark Rigor or v0.8.0 Harness Tax & Value) — the eval harness itself must run E2E and fail loud first
scope: ~3 phases (16-18), ~1 patch milestone
gates: [v0.7.0, v0.8.0]
---

# SEED-002: v0.6.2 "Make the Harness Real" — the eval harness runs E2E and fails loud

Committed milestone (patch bump after v0.6.1). This is the measurement counterpart to
v0.6.1: v0.6.1 made the *pipeline* honest (adapters do their namesake mechanism; the
Discipline stage can now fail). v0.6.2 makes the **eval harness** honest — the "harness of
harnesses" in `bench/` must run end-to-end, on real producers, and **fail loud instead of
silently measuring nothing or mislabeling what it measured.**

**Hard gate:** no further benchmarking (v0.7.0 retrieval rigor, v0.8.0 harness value) until
this ships. Benchmarking a harness that silently no-ops an arm or prints the wrong mode's
caveat produces numbers no one should trust — the same logic that deferred v0.7.0 behind
v0.6.1 ("benchmarking an enforcement layer that cannot fail measures nothing").

## Why This Matters — three E2E gaps found by a live spike (2026-07-10)

A throwaway spike (`scratchpad/distill_spike.py` + `seed_memory.py`) built the missing
memory→wiki distiller, seeded a fixture, and ran the real Track-2 harness
(`compound_eval --mode real --judge`) `none` vs `wiki`. The distilled-knowledge arm scored
**8.0 vs 6.5** on the Tier-2 judge, and the judge's rationale quoted facts that existed
*only* in the distilled wiki (`d≈0.29 null`, `17/20 vs 3/20`, `12k budget drops the pack`) —
so the mechanism works. But getting that one measurement surfaced three ways the harness is
**not** trustworthy E2E:

1. **The harness lies about its own mode.** `compound_eval --mode real` prints
   `CAVEAT: cheap mode validates the apparatus, not causation` and a generic
   `bench compounding trend` header — the caveat, `mode_note`, and report header do **not**
   reflect that real mode ran. A reader cannot tell a real result from a cheap smoke from the
   report. (`bench/compound_eval.py` / `bench/report.py`.)

2. **Arms silently measure nothing.** The `wiki` arm injects `_read_wiki_layer()` →
   `.planning/codebase/wiki.md`; when absent it returns `""`, so the arm reports a number for
   a wiki that was never there — no error, no warning. And there is **no producer** for it:
   `bench/wikigen.py` writes the single-file `wiki.md`, but the Phase-11 semantic retriever
   reads the **article directory** (`flowstate/context_prefix.py:54,64`) — generator ≠ reader
   (also flagged in [[SEED-001]] finding #2). A memory→wiki distiller does not exist at all
   (the spike is the first one). Same silent-no-op risk applies to the `pack` arm with no
   repomix pack.

3. **Verdicts are single-shot, no CIs.** `bench/judge.py::judge_run` returns the *first* good
   score; `compound_eval` emits one judge number per run with no repeated sampling and no
   confidence interval. The paired-bootstrap / Wilson / multi-judge machinery exists in
   `bench/grounding.py` and `bench/replicate.py` but is **not wired into the compound_eval
   path** — so the Track-2 loop cannot emit a defensible number E2E. (n=2 with no CI is
   exactly why the spike's 8.0-vs-6.5 is a *directional* signal, not a result.)

The intended E2E loop — *prior runs → distill → inject → judge with a CI* — is not closed by
any single command today. v0.6.2 closes it.

## Scope Estimate

**~3 phases (16-18), ~5 requirements.** Continues numbering after v0.6.1's Phase 15.
Downstream milestones shift: v0.7.0 renumbers to start after v0.6.2's last phase; v0.8.0
follows. This is plumbing/correctness only — **no measurement science, no verdicts, no
production wiring** (those stay in v0.8.0 / SEED-001).

- **Phase 16 — Mode-honest reporting (HAR-01).** `--mode real` never emits the cheap-mode
  caveat. Report header, `mode_note`, and caveat reflect the actual mode; every report states
  mode, arm, sample size (K/trials), and which producer artifacts were present. Deterministic,
  no LLM. Regression test asserts the real-mode report contains no cheap-mode string.

- **Phase 17 — No silent no-op arms + producers wired E2E (HAR-02, HAR-03).** Any arm whose
  required producer artifact is absent (`wiki`→wiki.md/article-corpus, `pack`→repomix pack)
  **fails loud** (or emits a prominent "arm measured nothing: producer X absent"), never a
  bare number. Ship the bench-side producers the readers actually consume: (a) promote the
  spike's **memory→wiki distiller** into `bench/`, and (b) fix the generator/reader mismatch
  so the **article corpus** the Phase-11 semantic retriever reads is produced (closes
  [[SEED-001]] #2 on the bench side). One `prepare-fixture` path generates what each arm needs
  before the arm matrix runs.

- **Phase 18 — Close the loop with a CI, E2E (HAR-04, HAR-05).** Wire multi-sample judging +
  paired-bootstrap CI into the `compound_eval` Track-2 path (reuse `grounding.py`/
  `replicate.py`, do not rebuild). One command runs *prior-runs → distill → inject → judge*
  on a fixture and returns a CI'd delta, not a single-shot score. Add a **green E2E smoke
  test** (cheap/deterministic, CI-safe) that exercises every arm's plumbing and asserts the
  harness fails loud on a missing producer — this is the "harness of harnesses works E2E"
  acceptance gate.

## Boundary with v0.8.0 / SEED-001 (explicit handoff)

v0.6.2 makes the harness able to run a trustworthy benchmark. v0.8.0 runs it and decides.

| Concern | v0.6.2 (this seed) — plumbing | v0.8.0 ([[SEED-001]]) — science |
|---|---|---|
| Wiki | bench-side producer + article corpus so the `wiki` arm runs E2E; fail loud when absent | **production** caller so the layer fires in real `flowstate` runs; manifest/staleness like `flowstate pack`; the value verdict |
| Judge | multi-sample + paired-bootstrap CI *wired into* compound_eval | judge-model ≠ producer-model **enforced**; evaluator-independence contract |
| Tax | (out of scope) | `BridgeResult.usage` + tokens/latency per arm; cost-per-success denominator |
| Verdict | (out of scope) | pre-registered rules; real-repo paired study; arm matrix with tax |

If v0.6.2 lands, v0.8.0's Phase 19/20 shrink to the *production* half (independence
enforcement + production wiki caller + tax), because the bench-side plumbing is already real.

## Breadcrumbs

Spike (promote, do not rebuild — currently throwaway in the session scratchpad):
- memory→wiki distiller — `scratchpad/distill_spike.py` (deterministic core + optional one-pass `--llm`)
- fixture seeder — `scratchpad/seed_memory.py` (10 true FlowState facts → memory.db)
- measurement recipe — `python -m bench.compound_eval --mode real --runs 2 --root <proj> --layers none|wiki --judge --allow-llm`

Already built — reuse:
- `_LAYERS_MAP` arms + `_run_one` include_layers monkeypatch — `bench/compound_eval.py:60-66,169-179`
- mode caveat / report rendering — `bench/report.py`; judge-excluded note at `:80`
- single-shot judge — `bench/judge.py::judge_run`
- multi-judge + `_wilson` + paired machinery — `bench/grounding.py:1136,267`; `bench/replicate.py:60-106`
- `paired_bootstrap` — `bench/stats.py` (from v0.7.0 Phase 12)
- wiki path constants (generator≠reader bug) — `flowstate/context_prefix.py:54` (`wiki.md`), `:64` (article dir)
- single-file wiki generator — `bench/wikigen.py`
- `scaffold(synthetic=False)` wipes `memory.db` — `bench/project.py:218-222` (why the memory arm starts empty)

Context docs: `bench/BENCHMARKING_SCOPE.md`, `bench/PAIRED_DESIGN_RUNBOOK.md`, `bench/BENCHMARK_HANDOFF.md`.

## Notes

Captured 2026-07-10 immediately after Phase 13 closed, prompted by a README-vs-reality audit +
the distill spike. Same integrity ethos as the rest of the milestone lattice: **the harness
must fail loud, name its mode honestly, and never report a number for an arm it did not
actually exercise.** A benchmark you cannot trust is worse than no benchmark. Ship this before
measuring anything further.
