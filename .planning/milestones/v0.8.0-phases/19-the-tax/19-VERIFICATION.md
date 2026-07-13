---
phase: 19-the-tax
verified: 2026-07-11T06:20:00Z
status: passed
score: 13/13 must-haves verified
overrides_applied: 0
---

# Phase 19: The Tax — Verification Report

**Phase Goal:** Every pipeline run can be measured for what it actually costs (tokens, cost, latency) instead of estimated — the accounting layer the harness has been missing since `bench/` began.
**Verified:** 2026-07-11T06:20:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | json-mode bridge call returns real usage + wall-clock duration | ✓ VERIFIED | `bridge.py:328-331` builds `BridgeUsage` from `input_tokens/output_tokens/cache_read_input_tokens`; `duration_s` from `time.monotonic()` window (`bridge.py:307-316,343`) |
| 2 | text-mode `.output` byte-identical, `usage=None` (no caller regression) | ✓ VERIFIED | Default path `output=result.stdout`, `usage=None` (`bridge.py:318-319`); JSON extraction gated behind `output_format=="json"`. Test `test_text_mode_output_byte_identical_and_usage_none` passes |
| 3 | malformed/absent json usage never raises, yields `usage=None` | ✓ VERIFIED | WR-01/WR-02 fixed: `isinstance(raw_usage, dict)` + `int(...or 0)` + `AttributeError` in except tuple (`bridge.py:324-335`). Independent spot-check: all 5 malformed shapes returned cleanly, `.output` always str |
| 4 | bridge instance exposes cumulative totals across all run() calls | ✓ VERIFIED | `total_tokens_in/out/cache_read/total_wall_clock_s` seeded `bridge.py:205-208`; `_accumulate()` folds at success return (`bridge.py:214-224,345`). Test `test_totals_sum_across_json_calls` passes |
| 5 | RunSnapshot records real tokens_in/out/cache_read/wall_clock_s per run | ✓ VERIFIED | `metrics.py:58-61` appends four fields with defaults; `capture.py:227-230` populates from RUN metadata |
| 6 | compute_scorecard byte-identical after new fields (Track-1 integrity) | ✓ VERIFIED | Fields read by no axis; `axis_enrichment` still consumes `prefix_tokens` (`metrics.py:153-154`). Score-unchanged test in `test_bench_compound.py` passes |
| 7 | prefix_tokens keeps Track-1 GROWTH role — NOT repurposed | ✓ VERIFIED | `metrics.py:51` distinct field, still `len(prefix)//_CHARS_PER_TOKEN` at `capture.py:205`; feeds `axis_enrichment` unchanged |
| 8 | real-mode pipeline surfaces bridge totals into RUN journal entry | ✓ VERIFIED | `orchestrator.py:328-337` passes `bridge.total_*` into `append_run_entry`; `journal.py:99-102` writes the four keys into metadata; `capture.py:153-160` reads them |
| 9 | cheap/dry runs leave consumption fields at 0/None | ✓ VERIFIED | Dry bridge accumulates nothing; `orchestrator.py:337` passes `wall_clock_s=None` on `dry_run`; `_zeroed_snapshot` sets 0/0/0/None (`capture.py:59-62`) |
| 10 | report shows per-arm total tokens + seconds alongside quality metrics | ✓ VERIFIED | `_tax_totals`/`_tax_block` (`report.py:64-102`); rendered in JSON (`:176`), Rich panel (`_tax_panel` :271, :364), markdown (`_tax_markdown_lines` :293, :339) |
| 11 | tax block explicitly labeled EXCLUDED from compounding_score | ✓ VERIFIED | `_TAX_NOTE = "Track-2 tax — EXCLUDED from compounding_score"` (`report.py:56`), carried in JSON/panel/markdown |
| 12 | tax numbers never touch metrics.py or compounding_score | ✓ VERIFIED | `report.py` imports only `Scorecard` (dataclass), no `compute_scorecard` reference; tax logic entirely in `report.py`. Score-unchanged test passes |
| 13 | cost-per-success divides tax by passed verify acceptance gates, named honestly (not "commit") | ✓ VERIFIED | `gates_passed = sum(verify_pass)` (`report.py:88`); label `"per verified acceptance gate"` (`:61`); "commit" appears only in warning comments, never in rendered output; zero-gate → "n/a" (`:90-95`) |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/bridge.py` | BridgeUsage + usage/duration_s + cumulative totals | ✓ VERIFIED | All present; WR-01/WR-02 fixes landed |
| `tests/test_bridge.py` | text byte-identical + json extract + malformed guard + cumulative tests | ✓ VERIFIED | Named tests present and passing incl. WR regression tests |
| `bench/metrics.py` | RunSnapshot with 4 consumption fields | ✓ VERIFIED | `:58-61` |
| `bench/capture.py` | reads 4 keys from RUN metadata | ✓ VERIFIED | `:153-160,227-230`; `_zeroed_snapshot` updated |
| `flowstate/journal.py` | RUN metadata carries 4 keys | ✓ VERIFIED | `:26-29,99-102` |
| `flowstate/orchestrator.py` | passes bridge totals into append_run_entry | ✓ VERIFIED | `:328-337` |
| `flowstate/tools/research.py`, `strategy.py` | 3 call sites output_format="json" | ✓ VERIFIED | research.py:111,139; strategy.py:154 |
| `bench/report.py` | tax block + cost-per-gate, Track-2 excluded | ✓ VERIFIED | `_tax_totals/_tax_block/_tax_panel/_tax_markdown_lines` |
| `tests/test_bench_compound.py`, `test_journal.py` | tax/consumption tests | ✓ VERIFIED | Pass (147 in targeted run) |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `ClaudeBridge.run` | usage.cache_read_input_tokens / input_tokens / output_tokens | `json.loads` on json path | ✓ WIRED (`bridge.py:323-331`) |
| `orchestrator.run_pipeline` | `journal.append_run_entry` | `bridge.total_*` kwargs into RUN metadata | ✓ WIRED (`orchestrator.py:334-337`) |
| `capture_run_snapshot` | RunSnapshot consumption fields | `metadata.get("wall_clock_s"...)` | ✓ WIRED (`capture.py:153-160,227-230`) |
| `report.py` tax block | RunSnapshot consumption + verify_pass | sum fields ÷ summed verify_pass | ✓ WIRED (`report.py:87-102`) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Never-raise on malformed usage JSON | Inline: 5 malformed shapes (non-dict list/str usage, null tokens, null result, garbage) through `ClaudeBridge.run(output_format="json")` | All returned cleanly, `.output` always str, no exception; usage=None or zeroed | ✓ PASS |
| Full test suite | `uv run python -m pytest -q` | 1141 passed, 91.17% coverage | ✓ PASS |
| Targeted phase tests | `pytest tests/test_bridge.py tests/test_journal.py tests/test_bench_compound.py` | 147 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TAX-01 | 19-01 | `ClaudeBridge.run()` captures real usage via json path, `.output` byte-identical | ✓ SATISFIED | Truths 1-4 |
| TAX-02 | 19-02 | `RunSnapshot` records real tokens/wall_clock_s, replacing prefix estimate as consumption source | ✓ SATISFIED | Truths 5-9 |
| TAX-03 | 19-03 | `bench/report.py` per-arm tokens/seconds, Track-2 excluded from compounding_score | ✓ SATISFIED | Truths 10-12 |
| TAX-04 | 19-03 | cost-per-success denominator = flowstate verify acceptance gates, named honestly | ✓ SATISFIED | Truth 13 |

No orphaned requirements — all 4 IDs mapped to Phase 19 in REQUIREMENTS.md and covered by plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bench/report.py` | 89 | Cost basis `total_tokens = tokens_in + tokens_out` omits `cache_read` (review IN-02) | ℹ️ Info | Intentional documented decision (19-03 key-decisions: billable = uncached tokens; cache_read shown separately). Not a gap |
| `bench/capture.py` | 160 | `isinstance(raw_wall, int|float)` admits bool (review IN-03) | ℹ️ Info | Unreachable via current producer (journal writes float|None). Defensive-hygiene only |
| `flowstate/bridge.py` | 334-335 | Redundant reassignment in except branch (review IN-01) | ℹ️ Info | Harmless; pre-try init already provides fallback |

No debt markers (TBD/FIXME/XXX) introduced. No stubs, no placeholder returns, no unwired artifacts.

### Human Verification Required

None. All contracts are deterministic and verifiable in-codebase (no UI, no external services, no live LLM calls in the accounting path — adapters switched to `output_format="json"` but Plan 01 guarantees byte-identical `.output`).

### Gaps Summary

No gaps. All 4 ROADMAP success criteria and all 4 TAX requirements are met. The three load-bearing contracts hold and were independently re-verified:

1. **19-01** — text-mode `.output` byte-identical; usage/duration_s populated only on json path; `run()` never raises on malformed usage JSON. WR-01/WR-02 fixes are on main (`63af2c3`, `ed2b7de`) with regression tests (`72e149b`); independent spot-check confirms the never-raise guarantee across all flagged edge cases.
2. **19-02** — `RunSnapshot` carries real consumption from bridge totals threaded orchestrator→journal→capture; `prefix_tokens` NOT repurposed; `compute_scorecard` byte-identical (proven by test).
3. **19-03** — tax block EXCLUDED from `compounding_score`, lives entirely in `report.py` (never imports/feeds `metrics.py`); cost line named "per verified acceptance gate" (denominator = summed `verify_pass`), never "commit".

Full suite: 1141 passed, 91.17% coverage (≥80% gate met). The three review Info findings (IN-01/02/03) are non-blocking and were deliberately deferred; IN-02 reflects a documented design decision, not a defect.

---

_Verified: 2026-07-11T06:20:00Z_
_Verifier: Claude (gsd-verifier)_
