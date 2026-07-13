---
phase: 22-the-verdict
artifact: pre-registration
requirement: VERD-01
status: frozen
written: 2026-07-11
seed: 20260711
---

> **FROZEN — do not amend after the first real trial.** Written 2026-07-11, before any
> `--mode real` run. This document is the pre-registered measurement protocol for the
> Phase 22 verdict. Its scientific value is entirely its commit-before-data ordering: every
> rule below (win threshold, arms, contrasts, correction, sample size, seed) is fixed here in
> writing so the verdict cannot be a post-hoc, data-peeked claim. Any later edit is visible in
> git blame and voids the pre-registration. A NULL result is a legitimate, accepted outcome —
> the run is NOT retried until significant.

# Phase 22 — The Verdict: Pre-Registration

This is a scientific pre-registration. It transcribes the locked decisions D-01..D-08 from
`22-CONTEXT.md` into a standalone frozen protocol. It restates those decisions; it does not
re-decide them.

## 1. Subject repo (D-01, D-01a)

The paired-design run executes against **`/Users/jhogan/floxybot2`** — a real, in-domain
Python AI system ("FloxBot: multi-channel context-aware support system for Flox users";
~232 tracked files, ~160 `.py`, ~1.3 MB source, with README and docs).

It was chosen because it is **pristine of FlowState/GSD planning artifacts**: no
`flowstate.json`, no `memory.db`, no `.planning/`, no root `PROJECT.md` / `ROADMAP.md` /
`research/`. The only `.claude/` present is the project's own Claude-Code config — legitimate
project content, NOT FlowState-generated output.

**Contamination control (D-01a).** The original candidate `bride_of_flinkenstein` was rejected:
it was itself created by FlowState, so its `research/` and docs were FlowState output — a
circular "tool reads its own homework" confound. `floxybot2` was never authored by FlowState,
which resolves the self-reading contamination at the source. The `.claude/` config may be swept
into the `pack` layer, but as legitimate project config it is not circular contamination.

**Never-mutate discipline (D-01).** `close_loop`/`verdict` operate on an **isolated worktree
copy** of `--root`. The real repo `/Users/jhogan/floxybot2` is **never mutated**. All writes go
to the worktree copy.

**Empty-memory control (naturally satisfied).** The compounding curve requires run 1 = empty
memory. `floxybot2` ships no `memory.db`, so run-1-empty-memory holds by construction. The
driver must verify that `close_loop`'s `scaffold()` seeds only its own baseline and that no
stray FlowState state leaks into the worktree.

## 2. Win rule (D-02) — the frozen COMBINED GATING rule

The driver (`bench/verdict.py`, built in Plan 02) implements this rule **VERBATIM**. This
document and `bench/verdict.py` MUST state this identical three-part rule; they must be
byte-consistent on the decision.

A treatment arm **WINS** iff, for its `(arm − none)` quality-delta contrast, **ALL THREE** of
the following hold:

| # | Gate | Condition |
|---|------|-----------|
| 1 | CI | the paired-bootstrap **95% CI excludes 0** |
| 2 | Effect size | **Cohen's d ≥ 0.8** (large effect) |
| 3 | Correction | the contrast **survives Holm-Bonferroni** across the 4 co-primary contrasts (GATING, not decorative) |

**Anything else = NULL.** A null is a valid, documented outcome that licenses stripping that
layer. Holm-Bonferroni (gate 3) is **gating**: a contrast that fails Holm cannot win regardless
of its raw CI or d.

**Explicitly forbidden:** no re-running to chase significance; no post-hoc rule changes. The
verdict is decided once, under these rules, on the pre-registered sample.

## 3. Endpoints (D-03)

Both endpoints are reported **per arm, side by side**.

| Endpoint | Definition | Source | Notes |
|----------|------------|--------|-------|
| **Quality** | Phase-20 independent multi-judge score (0–10) | `bench/judge.py::aggregate_judges` (with `_validate_judges`) | judge-model ≠ producer-model is enforced |
| **Tax** | per-arm `tokens_in` / `tokens_out` / `cache_read` + `wall_clock_s` | Phase-19 fields via `bench/report.py` Track-2 | **EXCLUDED** from `compounding_score` (Track-2, never contaminates the deterministic scorer) |

## 4. Arms and co-primary contrasts (D-05)

**Arms (5):** `none` · `pack` · `memory` · `wiki` · `full`.

**Co-primary endpoints (4 treatment-vs-none contrasts):**

| Contrast | Delta |
|----------|-------|
| pack − none | `pack` quality minus `none` quality |
| memory − none | `memory` quality minus `none` quality |
| wiki − none | `wiki` quality minus `none` quality |
| full − none | `full` quality minus `none` quality |

All four are co-primary and each is judged against the D-02 three-part rule.

## 5. Multiple-comparison correction (D-06)

Correction across the 4 co-primary contrasts = **Holm-Bonferroni** (FWER control, uniformly
more powerful than plain Bonferroni). It is **GATING** per D-02 gate 3: a contrast that does not
survive Holm **cannot win**, regardless of its raw CI or d.

**Both** raw and Holm-corrected significance are **reported** for transparency, but the WIN/null
decision uses the **Holm-corrected** result.

## 6. Compounding curve (D-07)

Report the compounding curve **run 1 → 3 per arm, paired-normalized to run-0** (subtract the
run-0 baseline per trial). wiki/memory value, if any, is expected **only at run 2+**, because
run 1 has empty memory. A flat run-1 wiki/memory delta is the expected, not-anomalous, shape.

## 7. Sample size and cost posture (D-08)

**Pre-registered n:** **trials = 5, runs = 3**, `--mode real`, **seed = 20260711** (pinned for
reproducibility).

**Sequence (mandatory order):**

1. `--mode cheap` plumbing check — free; proves the 4-contrast driver + Holm-Bonferroni + report
   run end-to-end.
2. **Cost estimate produced and explicitly greenlit by the user.**
3. The full **5 × 3** `--mode real` run.

Chosen posture is "straight to full 5×3" (no intermediate real smoke) — but the paid run does
**not** start until the estimate is shown and approved. Per the established `close_loop`
fail-loud discipline, a `--mode real` run that produced no usable paired trials exits non-zero;
it must never report a null CI as success.

## 8. Setup addendum — one-time repo grounding (2026-07-11)

**Setup-only note; does NOT amend the frozen decision rule, arms, or n.**

Before the sweep, the subject repo is grounded **once** on `--root` via an auto-derived
interview — a single bounded `claude --print` call (`bench/ground.py::ground_from_repo`,
`output_format="json"`, `allowed_tools=[]`, `max_turns=2`) that reads the repo's README + a
bounded structural summary and returns the interview fields (`core_problem`, `ten_x_vision`,
`architecture_pattern`, `milestones`, `research_focus`) — plus a repomix pack. Both are frozen
into `flowstate.json` / `.planning/codebase/repomix-pack.xml` and every `_worktree` copy
inherits them unchanged via `scaffold(synthetic=False)` (which mutates only `memory.db`).

**Why:** without it, `load_state` on a raw repo returns an empty interview, so every arm plans
a generic/empty project and the research arm discards every section — biasing all arms equally
toward null. Grounding gives research real substance to plan, **constant across all arms and
trials**; only the context layers (`none`/`pack`/`memory`/`wiki`/`full`) differ, which is
exactly what the arms test.

**Integrity:** the derivation is a ONE-TIME `--root` setup step, run **once before** the sweep
— **never per-trial** (a per-trial LLM call would vary across arms and confound the paired
design). It runs in `--mode real` only; `--mode cheap` never invokes it (stays free +
deterministic). This addendum documents setup **only**: it does **NOT** change the frozen D-02
decision rule (95% CI excludes 0 **AND** Cohen's d ≥ 0.8 **AND** survives Holm-Bonferroni), the
5 arms, the 4 co-primary contrasts, or the pre-registered n (trials = 5, runs = 3, seed = 20260711).

---

*Pre-registration for Phase 22 (v0.8.0 "Harness Tax & Value"). Frozen 2026-07-11. Committed
before any `--mode real` trial (D-04). §8 setup addendum appended 2026-07-11 — setup-only, the
frozen win rule / arms / n are unchanged.*
