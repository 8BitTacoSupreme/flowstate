# Phase 20: Evaluator Independence - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Make `bench/judge.py` refuse to grade its own producer's output, and turn a single judge call into a defensible multi-judge verdict — **without disturbing `bench/metrics.py`'s authority** as the deterministic scorer. Delivers IND-01 (fail-loud independence guard), IND-02 (multi-judge aggregation), IND-03 (a test proving `compounding_score` stays deterministic and the LLM judge stays excluded under the new path).

**Not in scope:** changing what `metrics.py` scores or how; the wiki layer (Phase 21); the actual verdict run (Phase 22). This phase only hardens the judge's independence and aggregation.

</domain>

<decisions>
## Implementation Decisions

### Aggregation shape (IND-02)
- **D-01:** Multi-judge output keeps the **0–10 granularity AND adds a binarized pass-rate with Wilson CI**. Report the mean (and/or median) of per-judge 0–10 scores, *and* binarize each judge's score at a pass threshold to compute a pass-rate with a Wilson confidence interval (reusing `grounding.py`'s `_wilson`). This satisfies ROADMAP SC#2 ("majority vote + Wilson CI, mirroring `grounding.py`") without discarding the numeric signal that `summarize()` trends on.
- **D-02:** The binarization threshold is a planning detail (a named constant, e.g. `≥7 = pass`), but it MUST be explicit and documented, not magic. `summarize()`'s existing trend logic continues to run on the numeric mean across runs; the pass-rate/Wilson CI is an *additional* per-run field, not a replacement.
- **Rationale (rejected alternatives):** "Binarize only" (literal mirror) was rejected because it throws away the 0–10 signal the compounding trend is built on. "Average only" was rejected because it doesn't deliver the Wilson-on-proportion pattern SC#2 names.

### Fail-loud boundary (IND-01)
- **D-03:** The independence guard fires at **config/validation time — a hard fail (raise / nonzero exit) BEFORE any judging starts.** Per-run `judge_run(...)` keeps its existing **never-raise → `None`-score** contract untouched. This cleanly separates *operator error* (you configured the eval to grade its own producer, or gave no judge) from *runtime judging failure* (a `claude` call failed → insufficient-data), which must stay soft so it never contaminates results.
- **D-04:** A same-model or absent judge is a **hard stop**, not a warning-and-continue — the entire point of the milestone is a *defensible* verdict, so a compromised judge configuration must not be allowed to produce numbers at all.

### Guard location (IND-01)
- **D-05:** Add an **argparse `main()` / `python -m bench.judge` CLI to `judge.py`** with `--judge-model` and `--producer-model`, enforcing the guard at parse/validate time. This makes IND-01's "running `bench/judge.py` with `--judge-model` absent" literal, and matches `grounding.py`, which is already a CLI. `judge.py`'s existing library functions (`judge_run`, `summarize`, etc.) stay importable and unchanged in contract.
- **D-06 (CORRECTED after plan-check — supersedes the original premise):** The shared validation (judge set non-empty; every judge ≠ producer) lives in a **reusable helper**, but the producer model is **passed explicitly**, NOT read from `RunSnapshot` — `RunSnapshot` has no producer field (Phase 19 added tokens/wall-clock only; the earlier assumption was wrong). The **real judged-run chokepoint is `bench/compound_eval.py`**, which both the direct CLI path and the `close_loop → replicate → subprocess` path flow through, and which already owns `--judge-model` (default `None`). Wire the guard there:
  - `compound_eval.py` gains `--producer-model` and calls the shared guard when judging is active (`do_judge` true). Per IND-01/D-04: `--judge` set but `--judge-model` absent, OR judge == producer → **fail loud (nonzero exit)** before any judging.
  - `bench/replicate.py::_run_trial` — the actual conduit — must thread an **explicit, distinct** `--judge-model` (and `--producer-model`) into the `compound_eval` subprocess command it builds, so the real replicate/close_loop path honors the guard AND stays runnable after it lands. `replicate.py` is therefore in scope (`files_modified`).
  - `close_loop.py` does **NOT** get a direct `judge_run` guard — it never calls `judge_run`; its real path is covered **transitively** through `compound_eval`. Only touch `close_loop.py` if it must pass model config down to `replicate`; otherwise leave it out of scope.
  - The guard must define its **unset/CLI-default-model semantics** explicitly and reconcile them with D-04 ("absent judge = hard stop") — the default real path must remain executable via a distinct judge/producer pairing (threaded through `replicate`), not raise on `judge==producer==None`.

### Judge set default (IND-02)
- **D-07:** Default to a **single judge** (backward-compatible with existing callers). When multiple judge models are passed, **every** judge model must differ from the producer model — not merely the aggregate. Any judge == producer → hard fail (per D-03/D-04).
- **D-08:** **Even-N ties resolve conservatively: a tie counts as fail** (e.g. 2/4 pass → not a majority pass). Documented alongside the threshold constant.

### Claude's Discretion
- Exact pass threshold value, the names of the validation helper and CLI flags, whether the aggregate field reports mean vs median (or both), and the precise JSON shape of the multi-judge summary — all planner/executor discretion, provided the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The code being changed
- `bench/judge.py` — the Tier-2 LLM-as-judge. Today a pure library: `judge_run(run_index, artifacts, fixture, *, model=None)` (single optional model, no producer awareness, no CLI), `summarize()` (numeric 0–10 trend), `JudgeResult` dataclass. Explicit **never-raise → None** contract (docstring lines 8–13). This phase adds the CLI + independence guard + multi-judge aggregation on top.

### The pattern to mirror (IND-02)
- `bench/grounding.py` — already ships the `--judge-models` list pattern this phase mirrors. Key references: `_wilson(successes, n)` (line 267 — **reuse this**, do not reimplement), the majority-vote shape (`yes = sum(v is True ...); majority = yes > len(judge_models)/2`, e.g. lines 506–515, 541–543), and its argparse CLI structure (line 64+). Note the mismatch this phase resolves: grounding's votes are **booleans**, judge's are **0–10 scores** — see D-01.

### The authority that must NOT move (IND-03)
- `bench/metrics.py` — `compute_scorecard` / `compounding_score` is the authoritative deterministic scorer; the LLM judge is and stays **excluded** from it. IND-03 requires a test asserting this holds under the new multi-judge path. (Phase 19 already established the "judge excluded" + "tax excluded" exclusion-note convention in `bench/report.py` — follow it.)

### The real judged-run chokepoint + conduit (D-06, corrected)
- `bench/compound_eval.py` — the real chokepoint. Already owns `--judge-model` (default `None`) and a `_should_judge`/`do_judge` gate; calls `judge_run`. The `--producer-model` flag + shared guard land here. `RunSnapshot` does **not** carry the producer model — pass it explicitly.
- `bench/replicate.py::_run_trial` — builds the `python -m bench.compound_eval --judge --allow-llm` subprocess command with **no** judge/producer model today. Must thread an explicit distinct `--judge-model`/`--producer-model` so the real path honors the guard and stays runnable. In scope.
- `bench/close_loop.py` — calls `replicate`, never `judge_run` directly; covered transitively via `compound_eval`. No direct guard. Touch only if it must pass model config to `replicate`.

### Milestone/phase spec
- `.planning/ROADMAP.md` §"Phase 20: Evaluator Independence" — goal + 3 success criteria.
- `.planning/REQUIREMENTS.md` — IND-01, IND-02, IND-03 traceability.
- `.planning/seeds/SEED-001-harness-tax-and-value.md` — full milestone rationale (evaluator independence half).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bench/grounding.py::_wilson(successes, n)` — Wilson CI helper; reuse directly for the binarized pass-rate (D-01). Do not reimplement.
- `bench/grounding.py` argparse `main` + `--judge-models` list parsing — structural template for judge.py's new CLI (D-05).
- `bench/judge.py::judge_run(..., *, model=...)` — already takes a per-call model; multi-judge is a loop over models calling this, then aggregating (keeps the never-raise contract per D-03).
- `RunSnapshot` (Phase 19) — carries the producer model + real consumption; the source of `--producer-model` / the guard's producer input at the caller (D-06).

### Established Patterns
- **Never-raise → None** is the judge/grounding runtime contract. The new guard must NOT violate it at judging time — it fires *before* judging (D-03).
- **Exclusion-note convention** (Phase 19, `bench/report.py`): Track-2 / judge outputs are explicitly marked EXCLUDED from `compounding_score`. IND-03's test enforces this stays true.
- **`metrics.py` is deterministic + authoritative; the LLM judge is advisory and excluded** — the invariant the whole milestone protects.

### Integration Points
- New `judge.py` CLI (`python -m bench.judge`) — the literal IND-01 surface.
- Shared validation helper called from both the CLI and `compound_eval.py` / `close_loop.py` (D-06).
- Multi-judge summary field flows into the report surface Phase 19 built (per-arm block), staying excluded from the scorer.

</code_context>

<specifics>
## Specific Ideas

- The `grounding.py` → `judge.py` mismatch (boolean votes vs 0–10 scores) is the crux: the resolution is "average the scores **and** binarize-for-Wilson," not one or the other (D-01).
- "Fail loud" means operator/config error is a hard nonzero exit; a failed `claude` judging call is still soft `None` (D-03). Keep these two failure modes distinct.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (The wiki activation and the paid verdict run are already scoped as Phases 21 and 22.)

</deferred>

---

*Phase: 20-evaluator-independence*
*Context gathered: 2026-07-11*
