# Phase 22 — The Verdict

- Mode: **real** · seed: 20260711 · trials: 5 · runs: 3
- Pre-registration (frozen before any real trial): `.planning/phases/22-the-verdict/22-PREREGISTRATION.md`
- Win rule (D-02, VERBATIM): D-02 three-part GATING rule: CI excludes 0 AND Cohen's d >= 0.8 AND survives Holm-Bonferroni across the 4 contrasts; else null.

## Pristine control (D-01a)

- PASS — subject `/private/tmp/claude-501/-Users-jhogan-frameworx-flowstate/8b9568d5-372b-410d-ad2e-ce964ac53276/scratchpad/floxybot2_subject` carries no stray FlowState state (no memory.db / flowstate.json / .planning / root PROJECT.md / ROADMAP.md / research).
- Run-1-empty-memory holds by construction; no self-reading confound (the project's own `.claude/` config is legitimate, not contamination).

## Per-arm quality + tax + compounding curve (D-03, D-07)

Quality = Phase-20 independent multi-judge mean (0-10, judge != producer). Tax is Track-2 and is EXCLUDED from any compounding score. The compounding curve is run 1->N paired-normalized to run-0 (wiki/memory value, if any, is expected only at run 2+ because run 1 has empty memory).

| Arm | Quality (0-10) | tokens_in | tokens_out | cache_read | wall_clock_s | Compounding curve (norm to run-0) |
| --- | --- | --- | --- | --- | --- | --- |
| none | 5.8 | 152 | 54091 | 2355382 | 935.138 | 0.0 -> 0.6 -> 0.6 |
| pack | 5.6 | 150 | 55978 | 2305980 | 954.135 | 0.0 -> 2.4 -> 1.8 |
| memory | 5.0667 | 134 | 52623 | 1939142 | 878.632 | 0.0 -> 0.6 -> 0.8 |
| wiki | 4.6 | 146 | 55146 | 2165132 | 936.875 | 0.0 -> 2.4 -> 1.2 |
| full | 5.7333 | 146 | 55002 | 2220517 | 935.13 | 0.0 -> 3.0 -> 2.2 |

## The 4 co-primary contrasts — D-02 three-part GATING rule (D-06)

A contrast PASSES iff its paired-bootstrap 95% CI excludes 0 AND Cohen's d >= 0.8 AND it survives Holm-Bonferroni across the 4 contrasts. Both raw and Holm-corrected significance are reported, but the WIN/null decision uses the Holm-corrected result (Holm is GATING, not decorative).

| Contrast | n | CI low | CI high | excludes 0 | Cohen's d | raw p | Holm p | VERDICT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pack - none | 5 | -0.8 | 3.4 | no | 0.47 | 0.298 | 1.0 | **NULL** |
| memory - none | 5 | -2.8 | 3.4 | no | 0.09 | 0.882 | 1.0 | **NULL** |
| wiki - none | 5 | -2.0 | 3.4 | no | 0.28 | 0.73 | 1.0 | **NULL** |
| full - none | 5 | -1.6 | 4.8 | no | 0.76 | 0.331 | 1.0 | **NULL** |

- `pack - none` = **NULL** — an accepted, documented outcome that licenses stripping this layer (no re-running to chase significance).
- `memory - none` = **NULL** — an accepted, documented outcome that licenses stripping this layer (no re-running to chase significance).
- `wiki - none` = **NULL** — an accepted, documented outcome that licenses stripping this layer (no re-running to chase significance).
- `full - none` = **NULL** — an accepted, documented outcome that licenses stripping this layer (no re-running to chase significance).
