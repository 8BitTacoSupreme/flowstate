---
status: passed
phase: 16-mode-honest-reporting
requirements: [HAR-01]
verified: 2026-07-11
---

# Phase 16 Verification — Mode-Honest Reporting

**Status: PASSED** (2/2 success criteria, HAR-01 complete). Verified by orchestrator via the passing regression suite + a live cheap-mode smoke.

## Success criteria

1. **A `--mode real` report (Rich + markdown + JSON) contains no cheap-mode caveat string; a regression test asserts it.** — VERIFIED. `bench/report.py` replaced the hardcoded `CAVEAT`/`mode_note`/table-title with mode-selected text; real mode emits a causal note with zero "cheap" occurrence. Regression tests (`test_render_report_real_mode_omits_cheap_caveat`, `test_write_json_real_mode_note_has_no_cheap`) assert no "cheap" substring across Rich, markdown, and JSON, and are part of the 1048-test suite that passes.

2. **Every report states mode, arm, sample size (K/trials), and producers-present.** — VERIFIED. Live cheap-mode smoke (`python -m bench.compound_eval --mode cheap --runs 2 --root bench/fixtures/sample_project --markdown`) rendered `mode=cheap · arm=full · K/trials=2 · producers-present=…` in the Rich header, the table title (`bench compounding trend — mode=cheap arm=full K/trials=2`), and the markdown record.

## Invariants held

- Cheap mode's caveat wording is preserved byte-for-byte (over-correction guard test passes; the live cheap smoke still shows the CAVEAT panel).
- Surgical: no change to the mechanical `CompoundingScore`, arms, or judge (CompoundingScore still computed in the smoke). No new deps.
- Full suite: 1048 passed @ 91.07% coverage.

## Notes

`bench/` is outside the `--cov=flowstate` denominator, so these report changes aren't measured by the coverage gate — but the bench report tests run and pass. No human verification items.
