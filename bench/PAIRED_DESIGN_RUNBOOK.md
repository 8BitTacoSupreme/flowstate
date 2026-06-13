# Paired-Design Run on a Real Repo — Runbook

Self-contained handoff for the next experiment: does FlowState's accumulating context
improve output **quality** on a real project, with the baseline-noise confound removed
and the **pack (RAG)** layer attributed separately from the **memory/gotchas
(compounding)** layers.

## Why this run (context)

Prior results on the synthetic `bench/fixtures/sample_project` (toy, near-ceiling ~6/10):
- Mechanical compounding **+3** (context demonstrably accumulates) — reproducible.
- Output-quality A/B (judge): K=3/N=5 → **null** (Cohen's d 0.29); K=8/N=10 → **d 0.62
  but an artifact** — driven by a noisy run-0 gap (on-arm started 5.0, off-arm 6.5), and
  in *absolute* quality the control ended **higher** (off 7.6 vs on 7.0).
- Verdict so far: **mechanism accumulates; no robust evidence it improves quality.**

Two confounds this run fixes:
1. **Cross-arm baseline noise** — separate trial sets gave the arms different run-0
   baselines. Fix: **normalize each trial to its own run-0** (paired within-trial).
2. **Pack vs compounding conflation** — `--inject on/off` toggles the *whole* prefix, so
   any gain mixes current-code RAG (pack) with accumulation (memory/gotchas). Fix: a
   **per-layer toggle** so RAG and compounding are attributed separately. Expectation
   (from the landscape): most quality gain on a large repo comes from the **pack/RAG**,
   not compounding; FTS5/BM25 retrieval over a large memory store is the suspected
   bottleneck for the compounding layers.

## Existing artifacts (all committed on `main`)
- `bench/compound_eval.py` — runner; has `--mode real --inject on|off --judge --allow-llm`.
  `_run_one(inject=...)` patches `flowstate.orchestrator.build_context_prefix` (whole-prefix
  on/off). `_worktree()` copies `--root` to a tmp dir per run (source stays pristine).
- `bench/judge.py` — Tier-2 LLM judge (scores artifacts vs fixture rubric; subprocess to
  `claude`, never-raises). `summarize()` gives trend.
- `bench/replicate.py` — N-trial driver; `_agg()` + `_cohens_d()`. Writes summary JSON.
- `bench/metrics.py` / `bench/capture.py` / `bench/report.py` — scorecard + snapshot + render.

## Prerequisite code changes (do these first)

### 1. Per-layer toggle in `bench/compound_eval.py`
Replace the binary `--inject on|off` with `--layers {full,none,pack,memory}`:
- `full` = current `inject=on` (all layers).
- `none` = current `inject=off` (empty prefix) — the control.
- `pack` = pack/fixtures only (current-code RAG; strip `## Gotchas`, `## Prior Knowledge`,
  `## Since Last Run`).
- `memory` = compounding layers only (strip the repomix pack + `## Eval Fixtures`).

Implementation: in `_run_one`, instead of patching `build_context_prefix` to `""`, patch it
to a **wrapper that calls the original then filters layers by `## ` heading**. Layers are
joined by `_SEPARATOR = "\n\n---\n\n"` (see `context_prefix.py`); split on it, keep/drop
blocks by their leading `## ` heading. Headings: `## Eval Fixtures` (fixtures), the pack
block is headerless XML, `## Gotchas`, `## Prior Knowledge` (memory, emitted by
`memory.py::get_context`), `## Since Last Run` (journal). Keep the no-raise discipline.
Add a unit test mirroring `test_run_one_inject_off_suppresses_and_restores` for each mode.

### 2. Within-trial normalization in `bench/replicate.py`
Add a `--paired` mode (or make it default): before aggregating, **subtract each trial's
run-0 score from its own scores** so trajectories start at 0. Aggregate the *normalized*
per-run means ±std and the normalized improvement. This cancels the cross-arm run-0 noise
that produced the spurious d=0.62. Keep raw numbers too for reference. Add the arm dimension:
loop over `--layers {full,pack,memory,none}` instead of just on/off.

### 3. (Optional, recommended) Multi-judge to cut noise
Judge std was ~1.3–1.8 on a 0–10 scale. In `judge.py`, run the judge with 2–3 models/seeds
(e.g. add `--judge-model` list) and average per run. Halves grading variance.

## Prepare the real project

1. Pick a real, complex repo with genuine headroom (a moderate Python OSS project, or one of
   your own). NOT the toy fixture.
2. Copy it to a scratch dir, then scaffold FlowState onto it:
   ```
   cp -R <real-repo> /tmp/fb_real && cd /tmp/fb_real
   flowstate kickoff   # writes .planning/ + fixtures/starter.json + runs pack (needs repomix!)
   ```
   Fill the interview with a real `core_problem`/`ten_x_vision`/`architecture_pattern`/
   `milestones` so research/strategy have substance (edit `flowstate.json` interview or
   answer kickoff prompts).
3. **Install repomix** (the pack layer needs it; it was absent in the prior env — only `npx`):
   `npm i -g repomix` or set `FLOWSTATE_REPOMIX_BIN`. Confirm `flowstate pack` succeeds (the
   pack layer is the main RAG lever — the prior runs never exercised it).
4. Confirm `flowstate.json` has an `install_manifest` with the pack entry (so `pack` layer +
   artifact-integrity verify axis are live).

**Disk/time note:** `_worktree()` copies the whole `--root` per run. For a large repo ×
(arms × N × K) copies this is heavy — consider excluding `.git`/`.venv`/build dirs from the
copy, or caching the pack so it isn't regenerated every run.

## Run procedure

```
# 4 arms × N=10 × K=8 (after wiring --layers + --paired):
python -m bench.replicate --layers full   --trials 10 --runs 8 --root /tmp/fb_real --paired --out /tmp/repl_full.json
python -m bench.replicate --layers pack   --trials 10 --runs 8 --root /tmp/fb_real --paired --out /tmp/repl_pack.json
python -m bench.replicate --layers memory --trials 10 --runs 8 --root /tmp/fb_real --paired --out /tmp/repl_memory.json
python -m bench.replicate --layers none   --trials 10 --runs 8 --root /tmp/fb_real --paired --out /tmp/repl_none.json
```
Run each in the background (each is ~8–12h; all four ≈ 1.5–2 days of wall time + large $).
**First do a cheap smoke** (`--trials 2 --runs 3`) per arm to validate wiring before the full run.

**Cost reality:** 4 × 10 × 8 = 320 live pipeline runs + judge calls. To cut cost: start with
3 arms (`full`, `pack`, `none`) at N=6/K=6, expand only if signal appears.

## Interpretation (the attribution that answers the question)

Compare normalized improvement (mean ±std, Cohen's d vs `none`):
- **`pack` − `none`** = value of current-code **RAG**. Expected to be the largest, positive.
- **`memory` − `none`** = value of **compounding** (memory/gotchas) alone. The open question.
- **`full` − `pack`** = compounding's **marginal** value on top of RAG. This is the real
  "does the compounding loop add anything" number.

Verdict rules:
- Real compounding effect ⟺ `memory`>`none` AND `full`>`pack`, **d ≳ 0.8**, non-overlapping
  CIs, on the **normalized** metric (and ideally absolute final quality, not just improvement).
- If `full ≈ pack` and `memory ≈ none` → compounding adds nothing; FlowState's value on a real
  repo is the pack/RAG (well-established), not the accumulation. (Most likely outcome given
  the FTS5-retrieval bottleneck hypothesis.)

## If compounding is null again — the upgrade path (from the systems landscape)
- **Selective injection** (ExpeL/AWM-style): only retain gotchas/memories that *demonstrably*
  improved a later run, instead of injecting everything.
- **Better retrieval**: replace FTS5/BM25 with semantic/graph memory (Zep/Mem0-class) — the
  suspected bottleneck at scale.
- **Metric optimization**: use the judge score as a DSPy/TextGrad objective over the prefix.
- **Verification/search**: add an AlphaCodium/best-of-N+verifier loop — the lever that
  reliably lifts code quality and that FlowState currently lacks.

## State at handoff
- `main` clean; 1 unpushed commit (`2f4d408`, the replicate driver) + this runbook.
- `featurebench-integration` branch local-only (Phase B adapter; run abandoned on disk).
- Prior results live in conversation only; `/tmp/flowstate_replication*.json` are ephemeral.
