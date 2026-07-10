# Paired-Design Run on a Real Repo — Runbook

Self-contained handoff for the next experiment: does FlowState's accumulating context
improve output **quality** on a real project, with the baseline-noise confound removed
and the **pack (RAG)** layer attributed separately from the **memory/gotchas
(compounding)** layers.

**See also:** `BENCHMARKING_SCOPE.md` (the two-track model — what a Track-2 harness-value
result like this one can and cannot license) and `BENCHMARK_HANDOFF.md` (Track-1
retrieval-ranking measured results).

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
   **per-layer toggle** so RAG and compounding are attributed separately. ~~Expectation
   (from the landscape): most quality gain on a large repo comes from the **pack/RAG**,
   not compounding; FTS5/BM25 retrieval over a large memory store is the suspected
   bottleneck for the compounding layers.~~ **SUPERSEDED** — the later grounding bench
   measured raw code pack ≈ none (no gain), while distilled wiki + semantic retrieval hit
   0.825 ≈ oracle 0.800 (surfaced the right article 17/20 vs BM25's 3/20). The gain does
   not come from the raw code pack; it comes from distilled knowledge + semantic
   retrieval. See "Corrected expectation" below.

## Existing artifacts (all committed on `main`)
- `bench/compound_eval.py` — runner; `--mode cheap|real --layers {full,none,pack,memory,wiki}
  --judge --allow-llm`. `_run_one()` monkeypatches `orch.build_context_prefix` with a wrapper
  that sets `include_layers` (`:169-179`); the `full` arm patches nothing. `_worktree()` copies
  `--root` to a tmp dir per run (source stays pristine). **Note:** the binary `--inject on|off`
  and `_run_one(inject=...)` described in earlier revisions of this runbook no longer exist —
  see "Prerequisite code changes" §1.
- `bench/judge.py` — Tier-2 LLM judge (scores artifacts vs fixture rubric; subprocess to
  `claude`, never-raises). `summarize()` gives trend. Single judge model — see §3.
- `bench/replicate.py` — N-trial driver; `_agg()` + `_cohens_d()` + `_paired_normalize()`.
  Writes summary JSON.
- `bench/metrics.py` / `bench/capture.py` / `bench/report.py` — scorecard + snapshot + render.
  `metrics.py` is the **authoritative deterministic** score; the LLM judge is excluded from it.

## Prerequisite code changes

Status as of 2026-07-10: **#1 and #2 are LANDED.** #3 is the only remaining unbuilt item.

### 1. Per-layer toggle in `bench/compound_eval.py` — **LANDED**
`_LAYERS_MAP` at `bench/compound_eval.py:60-66` replaces the binary `--inject on|off`
with `--layers {full,none,pack,memory,wiki}` (a `wiki` arm was also added, beyond the
original proposal). The shipped implementation is **better** than what this runbook
originally proposed: it threads a first-class `include_layers` kwarg into
`build_context_prefix` at assembly time via a monkeypatch in `_run_one`
(`bench/compound_eval.py:169-179`), rather than the post-hoc `## `-heading string
filtering originally suggested below (kept for historical reference, superseded):

<details><summary>Original proposal (superseded — see above)</summary>

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

</details>

### 2. Within-trial normalization in `bench/replicate.py` — **LANDED**
`_paired_normalize` at `bench/replicate.py:60-67` (`[[s - t[0] for s in t] for t in
trials]`) subtracts each trial's run-0 score from its own scores so trajectories start
at 0, cancelling the cross-arm run-0 noise that produced the spurious d=0.62. Raw and
paired metrics are both computed; the `--paired` flag selects which drives Cohen's d.
The `--layers` arm dimension ships as a `nargs="+"` list at `bench/replicate.py:100-106`
(default: all four of `full`, `pack`, `memory`, `none`; `wiki` also selectable).

### 3. Multi-judge to cut noise — **STILL UNBUILT** (the only remaining item)
Judge std was ~1.3–1.8 on a 0–10 scale. `bench/judge.py` still runs a single judge model
per run. `bench/grounding.py` already has the pattern to copy: `--judge-models` default
`"sonnet,sonnet,opus"` at `bench/grounding.py:1136`, majority vote + `_wilson`. Port that
pattern into `judge.py` to halve grading variance before the next real-repo run.

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

## Corrected expectation: where the gain actually comes from

The original "most quality gain on a large repo comes from the pack/RAG" expectation
(see "Two confounds this run fixes" above) is **superseded**. The later grounding bench
measured: raw code pack ≈ none (no gain over the vanilla control); distilled wiki +
semantic retrieval hit **0.825 ≈ oracle 0.800** (full recovery), surfacing the right
article **17/20** vs BM25's **3/20**. The `wiki` arm added to `_LAYERS_MAP`
(`bench/compound_eval.py:65`) exists for exactly this reason.

**The wiki gap (WIKI-F1, deferred):** the one layer with a proven lift never fires in
production. No `flowstate/` module passes `include_layers={"wiki"}` — every caller is a
bench/test driver. Neither `.planning/codebase/wiki.md` nor `.planning/codebase/wiki/`
exists on disk, so there is no corpus to retrieve from even if a caller wired it up.
There is also a **corpus-shape mismatch**: `bench/wikigen.py` writes the single-file
`wiki.md`, while the Phase-11 semantic wiki retriever reads the ARTICLE DIRECTORY
`.planning/codebase/wiki` (`flowstate/context_prefix.py:54,64` — `_WIKI_PATH` is the
single file, `_WIKI_CORPUS_DIR` is the directory the retriever actually consumes). Fixing
the wiki no-caller/no-corpus/shape-mismatch gap is a prerequisite to any real-repo run
that wants to test the wiki arm, not just `pack`/`memory`/`none`.

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
