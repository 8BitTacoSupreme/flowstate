# Phase 22: The Verdict - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning
**Source:** discuss-phase (interactive — this is a PRE-REGISTRATION; the rules below are fixed before any data is seen)

<domain>
## Phase Boundary

The capstone of v0.8.0. Using the three primitives shipped in phases 19–21 (real tax accounting, the independent multi-judge, the now-firing wiki layer), run a **pre-registered, paired-design measurement** on a **real repo** that honestly answers: does FlowState's context stack — each arm, and specifically the wiki — earn its token/latency tax? **A null result is a legitimate, accepted outcome** that licenses stripping a layer; the run is NOT retried until significant. VERD-01 (pre-register the rules), VERD-02 (run the paired design on a real repo across 5 arms with the compounding curve), VERD-03 (report quality AND tax per arm, apply the rules, accept null).

**In scope:** write + commit the pre-registration BEFORE the run; a light driver that runs the 4 treatment-vs-none contrasts via `bench/close_loop.py`/`replicate.py` in `--mode real`, applies the pre-registered rules with multiple-comparison correction, and writes the verdict report (quality + tax per arm + compounding curve).
**Out of scope:** changing the scorer, judge, or tax mechanisms (locked in 19–21); the v0.9.0 sandbox track; retrying/tuning to chase significance (explicitly forbidden — pre-registration integrity).

</domain>

<decisions>
## Implementation Decisions (the pre-registration)

### Subject repo (VERD-02)
- **D-01:** The paired run executes against **`/Users/jhogan/bride_of_flinkenstein`** — a real, in-domain repo (JS/Node frontend+backend Flink app with Avro schemas, ~103 tracked files, README + docs). `close_loop` operates on an **isolated worktree copy** of `--root`; the real repo is never mutated.
- **D-01a (control — must resolve before the run):** the subject repo **already contains FlowState state** (`flowstate.json`, `memory.db`, `research/`). The compounding curve requires **run 1 = empty memory**. The run MUST start from a **clean/pristine memory state** (exclude or reset the checked-in `memory.db` in the worktree copy) so accumulation is measured from zero, not from prior dogfood residue. Verify `close_loop`'s `scaffold()` seeds its own baseline and confirm the repo's `memory.db` does not leak into the measured runs; if it can, strip it in the worktree before trials.

### Pre-registered win rule (VERD-01) — committed before the run
- **D-02:** A treatment arm **wins** iff, for its `(arm − none)` quality-delta contrast, the **paired-bootstrap 95% CI excludes 0 AND Cohen's d ≥ 0.8** (large effect). Anything else = **null**, documented as a valid outcome that licenses stripping that layer.
- **D-03:** **Quality endpoint** = the Phase-20 independent multi-judge score (0–10; `bench/judge.py::aggregate_judges`, judge-model ≠ producer-model enforced). **Tax** = Phase-19 per-arm `tokens_in`/`tokens_out`/`cache_read` + `wall_clock_s` (`bench/report.py` Track-2, EXCLUDED from `compounding_score`). The verdict reports **quality AND tax per arm** side by side.
- **D-04:** These rules are written into a **committed pre-registration artifact** (`22-PREREGISTRATION.md`) **before** the first real trial runs. No post-hoc rule changes; no re-running to chase significance.

### Arms, contrasts & correction (VERD-02/03)
- **D-05:** Arms = **`none` · `pack` · `memory` · `wiki` · `full`**. **Co-primary** endpoints = each of the 4 treatment arms vs the `none` baseline (`pack−none`, `memory−none`, `wiki−none`, `full−none`) — all judged against the D-02 rule.
- **D-06:** Multiple-comparison correction across the 4 co-primary contrasts = **Holm-Bonferroni** (FWER control, uniformly more powerful than plain Bonferroni). *[Locked default — override here if you want Bonferroni or BH-FDR.]* Apply Holm to the CI/p-values; report both raw and corrected.
- **D-07:** Report the **compounding curve** run 1→N per arm (paired-normalized to run-0), showing that wiki/memory value, if any, appears only run 2+ (run 1 has empty memory).

### Sample size & cost posture
- **D-08:** Pre-registered n = **trials = 5, runs = 3**, `--mode real`, **seed pinned** (reproducibility). Sequence: (1) `--mode cheap` plumbing check (free, proves the 4-contrast driver + Holm + report end-to-end); (2) **cost estimate produced and greenlit by the user**; (3) the full real run. *Chosen posture is "straight to full 5×3" (no intermediate real smoke) — but the paid run does not start until the estimate is shown and approved.*

### Claude's Discretion
- Whether the 4-contrast sweep is a new thin driver over `close_loop`/`replicate` or an added `--sweep` mode; the exact verdict-report format; the seed value; how the pristine-memory reset in D-01a is implemented — planner/executor discretion, provided D-01a, D-02, D-06, and the pre-commit-before-run ordering (D-04) hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The run harness (VERD-02)
- `bench/close_loop.py` — `--root/--arm/--baseline/--trials(5)/--runs(3)/--mode{cheap,real}/--seed/--out`; prior-runs→distill→inject→judge→paired-bootstrap CI on an isolated worktree copy of `--root`; `--mode real` reuses `replicate._run_trial` (live LLM cost); `scaffold()` seeds baseline memory before `prepare_fixture`. Only `pack`/`wiki` arms have real producers to provision.
- `bench/replicate.py` — N-arm engine: `--trials/--runs/--layers`, `_paired_normalize` (subtract run-0), `_cohens_d`, `_per_trial_improvements` (pairs arms by trial index, drops incomplete pairs), imports `paired_bootstrap_ci`.
- `bench/bootstrap.py::paired_bootstrap_ci` (line 22) — the paired CI (Phase-18 seeded, mispairing-fixed). The correction (D-06) wraps this across 4 contrasts.
- `bench/prepare_fixture.py`, `bench/project.py::scaffold` — provision arms / seed memory in the worktree.

### Quality + tax (locked in 19–21 — do NOT modify)
- `bench/judge.py::aggregate_judges` (line 197) + `_validate_judges` (178) — the Phase-20 independent multi-judge (0–10, judge≠producer). Quality endpoint.
- `bench/metrics.py` — `compute_scorecard`/`compounding_score` (deterministic, judge EXCLUDED); `RunSnapshot` carries the real tax fields.
- `bench/report.py` — `_tax_totals` / `_TAX_NOTE` (Track-2 tax, EXCLUDED from score). Tax endpoint.

### Spec
- `.planning/ROADMAP.md` §"Phase 22: The Verdict" — goal + 3 success criteria + the "expensive; smoke before scaling" note.
- `.planning/REQUIREMENTS.md` — VERD-01/02/03. `.planning/seeds/SEED-001-harness-tax-and-value.md` — milestone rationale + cost-reality note.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- The entire measurement stack already exists: `close_loop` (compounding loop + paired CI), `replicate` (Cohen's d + per-trial pairing), `bootstrap.paired_bootstrap_ci`, `judge.aggregate_judges` (independent), `report` (tax). Phase 22 orchestrates + interprets them; it should add minimal new code (a 4-contrast driver + Holm + verdict report), not new measurement primitives.

### Established Patterns
- **Fail-loud on "measured nothing"**: `close_loop` exits non-zero if `--mode real` produced no usable paired trials (no bridge / all trials dropped) — a real run that measured nothing must never report a null CI as success. The verdict driver must inherit this.
- **Track-2 exclusion**: judge + tax are Track-2, excluded from the deterministic `compounding_score`. The verdict reports them explicitly as the quality/tax endpoints; they never contaminate the scorer.
- **Isolated worktree**: writes go to a copy of `--root`, never the real repo (D-01).

### Integration Points
- New thin driver (name TBD) that runs the 4 treatment-vs-none contrasts, applies Holm-Bonferroni (D-06), and emits `22-VERDICT.md` (quality + tax per arm + compounding curve + pass/null per the pre-registered rules).
- `22-PREREGISTRATION.md` committed before the run (D-04).

</code_context>

<specifics>
## Specific Ideas

- The pre-registration ordering is load-bearing: **commit `22-PREREGISTRATION.md` before the first real trial.** A verdict whose rules were written after seeing data is worthless.
- The subject repo's pre-existing `memory.db` is the single most likely confound (D-01a) — resolve it before scaling to the paid run.
- The paid run is the milestone's one real spend: cheap plumbing check → **cost estimate + user greenlight** → full 5×3 real (D-08).

</specifics>

<deferred>
## Deferred Ideas

- Auto-distill-at-end-of-run (deferred from Phase 21) is unrelated to the verdict and stays deferred.
- The v0.9.0 sandbox guardrail (SEED-003, spike passed) is a separate track — not this phase.

</deferred>

---

*Phase: 22-the-verdict*
*Context gathered: 2026-07-11 (pre-registration — rules fixed before data)*
