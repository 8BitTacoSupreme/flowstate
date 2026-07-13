---
status: complete
phase: 22-the-verdict
plan: 03
requirements: [VERD-02, VERD-03]
completed: 2026-07-12
---

# 22-03 Summary — The Verdict (paid 5×3 real run)

**Status:** complete — the pre-registered paired-design verdict was produced on a real repo and is a documented NULL. VERD-02 and VERD-03 met; v0.8.0's headline question is answered.

## What ran

The single owed paid run of the milestone: `bench.verdict --mode real --trials 5 --runs 3 --seed 20260711`, all 5 arms (none/pack/memory/wiki/full), independent judge (judge ≠ producer). **Wall-clock 1h33m** (measured; the earlier 5–7 hr estimate was conservative). Human-gated per D-08: a free plumbing/pristine pre-flight (Task 1) + a real trials=1 re-verification smoke, then explicit user greenlight before the paid run.

## Result — NULL across all 4 co-primary contrasts (accepted, D-02)

Per the frozen D-02 three-part gate (paired-bootstrap 95% CI excludes 0 AND Cohen's d ≥ 0.8 AND survives Holm-Bonferroni), **no treatment arm beat the `none` baseline**:

| Contrast | CI | Cohen's d | Holm p | Verdict |
|----------|-----|-----------|--------|---------|
| pack − none | [−0.8, 3.4] | 0.47 | 1.0 | NULL |
| memory − none | [−2.8, 3.4] | 0.09 | 1.0 | NULL |
| wiki − none | [−2.0, 3.4] | 0.28 | 1.0 | NULL |
| full − none | [−1.6, 4.8] | 0.76 | 1.0 | NULL |

Per-arm mean quality (0–10): none **5.8** (highest), full 5.73, pack 5.6, memory 5.07, wiki 4.6. `full − none` came closest (d=0.76, just under the 0.8 gate) but its CI straddles 0. Every arm carries comparable tax (~52–56k output tokens, ~1.9–2.4M cache_read/arm) — the layers add cost without a defensible quality lift.

This is a **pre-registered, accepted null**: it licenses stripping the context layers and was **not re-run to chase significance** (D-02/VERD-03). It corroborates prior evidence (pack ≈ none; the earlier compounding d=1.46 was an artifact).

## Integrity controls (honored)

- **D-01a pristine control:** PASS — embedded in `22-VERDICT.md`; run-1-empty-memory held by construction.
- **D-01 never-mutate-subject:** the run executed against a **pristine rsync snapshot** of `/Users/jhogan/floxybot2` in the session scratchpad (excluding `.venv`/`node_modules`), NOT the live repo. This deviates from the plan's literal `--root /Users/jhogan/floxybot2` **to better honor** the plan's own never-mutate invariant: `bench.verdict` grounds `--root` in place (writes `flowstate.json` + a pack), which would have contaminated the real repo and broken its pristine control. The real floxybot2 was verified untouched after the run.
- **D-04 pre-registration precedes run:** `22-PREREGISTRATION.md` committed (`a1f09aa`) before the first real trial.
- **Fail-loud:** the run completed with paired data on every contrast (no `_EXIT_NO_PAIRED_DATA`); research produced grounded, kept content on all 75 runs (`kept=1 discarded=0`), confirming the `260711-research-grounding-fix` holds at scale.

## Artifact

- `.planning/phases/22-the-verdict/22-VERDICT.md` — the frozen verdict (as written by the driver).
