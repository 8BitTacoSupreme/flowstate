# Phase 22: The Verdict - Discussion Log

> **Audit trail only.** Not consumed by downstream agents (they read CONTEXT.md). This is a PRE-REGISTRATION — decisions fixed before data.

**Date:** 2026-07-11
**Phase:** 22-the-verdict
**Mode:** interactive (deliberately NOT --auto — pre-registration decisions are the user's scientific-design calls)
**Areas discussed:** subject repo, win rule, cost posture, arm set/endpoint, correction method

---

## Subject repo (VERD-02)

| Option | Selected |
|--------|----------|
| FlowState on itself (dogfood) | |
| A different real repo | ✓ |
| Neutral OSS checkout | |

**User's choice:** a different real repo → **`/Users/jhogan/bride_of_flinkenstein`** (in-domain JS/Node Flink app, ~103 files, Avro schemas). **Note flagged:** repo already contains FlowState state (`flowstate.json`, `memory.db`, `research/`) → must start from clean memory for the compounding curve (D-01a).

## Pre-registered win rule (VERD-01)

| Option | Selected |
|--------|----------|
| CI-excludes-0 AND d≥0.5 | |
| CI-excludes-0 AND d≥0.8 (large effect) | ✓ |
| CI-only (exclude 0) | |

**User's choice:** stricter — win iff paired-bootstrap 95% CI(arm−none) excludes 0 AND Cohen's d ≥ 0.8.

## Cost posture

| Option | Selected |
|--------|----------|
| Smoke → then full n | |
| Reduced full run (3×3) | |
| Straight to full 5×3 | ✓ |

**User's choice:** straight to full 5×3 real (after a free cheap plumbing check). **Guardrail retained:** cost estimate shown + greenlit before the paid run starts.

## Arm set & endpoint (VERD-02/03)

| Option | Selected |
|--------|----------|
| 5 arms, primary = wiki−none | |
| wiki−none only | |
| 5 arms, all pairwise vs none (co-primary) | ✓ |

**User's choice:** all 5 arms (none/pack/memory/wiki/full), each treatment−none co-primary, with multiple-comparison correction.

## Correction method

**Claude's discretion (locked default, override available):** Holm-Bonferroni across the 4 co-primary contrasts (FWER control, uniformly more powerful than plain Bonferroni). Report raw + corrected.

## Deferred Ideas

- Auto-distill-at-end-of-run (Phase 21 deferral) — unrelated, stays deferred.
- v0.9.0 sandbox guardrail (SEED-003) — separate track.
