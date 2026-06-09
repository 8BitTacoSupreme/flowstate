---
status: complete
phase: quick-260609-j0g
plan: 01
subsystem: bench
tags: [compounding, eval, harness, bench, metrics, capture]
requires: [flowstate.metrics, flowstate.context_prefix, flowstate.verify, flowstate.memory, flowstate.gotchas, flowstate.context, flowstate.orchestrator, flowstate.state]
provides: [bench.metrics, bench.capture, bench.project, bench.compound_eval, bench.report, bench.fixtures.sample_project]
affects: []
tech-stack:
  added: []
  patterns: [pure-no-IO-metrics, never-raises-reads, single-source-constant-with-drift-test, argparse-runner, deterministic-json]
key-files:
  created:
    - bench/__init__.py
    - bench/metrics.py
    - bench/capture.py
    - bench/project.py
    - bench/compound_eval.py
    - bench/report.py
    - bench/fixtures/sample_project/flowstate.json
    - bench/fixtures/sample_project/.planning/fixtures/starter.json
    - bench/fixtures/sample_project/.planning/phases/01-foundation/01-VERIFICATION.md
    - bench/fixtures/sample_project/.planning/artifacts/work.txt
    - tests/test_bench_compound.py
  modified: []
decisions:
  - "## Prior Knowledge heading is emitted by MemoryStore.get_context (memory.py), NOT context_prefix.py — drift test scans the union of both emitter modules"
  - "Gotcha new-vs-reencounter attribution is run_id-first; created_at window is an explicit optional fallback parameter, NOT a field on the pure RunSnapshot dataclass"
  - "fixture flowstate.json is force-added past the root .gitignore (line 9: flowstate.json)"
  - "convergence axis stays flat under cheap-dry (dry run writes no RUN journal artifacts_changed) — the cheap-seed e2e exercises it by seeding RUN entries; this is honest, not a bug"
metrics:
  duration: ~50m
  completed: 2026-06-09
  tasks: 4
  files: 11
---

# Phase A Plan 01: Intrinsic Compounding Harness Summary

Standalone `bench/` package that measures whether FlowState run N+1 beats run N on the same project, using signals FlowState already exposes (journal artifact deltas, gotcha dedup, verify gates, prefix enrichment) — a pure-Python, CI-cheap regression guard for the compounding *measurement apparatus*, with an explicit caveat that only `--mode real` tests causation.

## What Was Built

- **`bench/metrics.py`** — Pure no-IO core: `RunSnapshot` dataclass, four axis functions (`axis_convergence`, `axis_gotcha_learning`, `axis_verify_non_regression`, `axis_enrichment`), and `compute_scorecard`. `CompoundingScore = (#compounding) − (#regressing)` clamped to `[−4,+4]`; `verdict == "compounding"` iff score ≥ +2 AND enrichment compounding AND no axis regressing. K=1 and empty inputs yield all-flat/insufficient-data, never raise.
- **`bench/capture.py`** — `capture_run_snapshot(root, probe_query, prior=None, *, run_id="", window_start=None)`: pure substrate reads (latest RUN journal entry, `get_gotchas`, `search`, `run_verify`, `build_context_prefix`) wrapped so it never raises (degrades to a zeroed snapshot). Single `_LAYER_HEADINGS` constant; gotcha attribution is run_id-first with a created_at-window fallback; pack layer detected via XML tag presence (headerless).
- **`bench/project.py`** — `scaffold(root)` (idempotent: starter.json + flowstate.json with install_manifest + 01-VERIFICATION.md gaps section + a checksummed work.txt) and `mutate_for_run(root, i)` (deterministic, resolves one gap per run index, shrinks the artifact body).
- **`bench/compound_eval.py`** — stdlib `argparse` runner (`python -m bench.compound_eval`), cheap/real mode dispatch, K-run loop, guarded spec-only `--judge` stub (refuses unless `--mode real` + `--allow-llm`, excluded from the mechanical score).
- **`bench/report.py`** — `write_json` (deterministic `sort_keys` + indent), `render_report` (honest caveat header first, then Rich trend table + scorecard panel, optional markdown record).
- **`bench/fixtures/sample_project/`** — checked-in self-consistent synthetic target.
- **`tests/test_bench_compound.py`** — 32 tests: metric-core (axes fire / detect regression / K=1 / never-raises), heading-drift coupling guard, capture never-raises + gotcha attribution, scaffold idempotency + harvest feed, mutate determinism, report caveat + render, judge refusal, cheap-seed 3-iteration e2e, cheap-dry smoke on a fixture copy, JSON determinism.

## Tasks & Commits

| Task | Description | Commit |
| ---- | ----------- | ------ |
| 1 | metrics core (RunSnapshot, 4 axes, scorecard) | `4590f99` |
| 2 | capture (pure reads) + project (scaffold/mutate) | `0ec3d99` |
| 3 | runner (argparse) + report (JSON/Rich/caveat) | `8af64f1` |
| 4 | sample_project fixture + e2e/smoke tests | `3079fa8` |

## Verification

- `python -m pytest tests/test_bench_compound.py -q` — 32 passed.
- `python -m pytest tests/ --cov=flowstate --cov-fail-under=80 -q` — 581 passed, flowstate coverage **92.28%** (gate held).
- `ruff check bench/ tests/` + `ruff format --check bench/ tests/` — clean.
- `python -m bench.compound_eval --mode cheap --runs 5 --root <copy of fixture>` — prints caveat + trend table + scorecard panel, exit 0; verdict `compounding` (Enrichment + Gotcha-learning fire).
- `grep -rc 'import.*flowstate.bridge' bench/` — **0** (harness never imports the bridge).
- No `flowstate/` source modified by any of the four commits.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Heading-drift test scanned the wrong source module**
- **Found during:** Task 2
- **Issue:** The plan's interface note implied all four `_LAYER_HEADINGS` strings appear in `context_prefix.py`, but `## Prior Knowledge` is actually emitted by `MemoryStore.get_context` in `memory.py`. A naive substring scan of `context_prefix.py` alone failed.
- **Fix:** The drift guard now scans the union of both emitter modules (`context_prefix.py` + `memory.py`), so it still fails loudly if any heading drifts at its true origin.
- **Files modified:** tests/test_bench_compound.py, bench/capture.py (doc comment)
- **Commit:** `0ec3d99`

**2. [Rule 3 — Blocking] Fixture flowstate.json is gitignored**
- **Found during:** Task 4
- **Issue:** The root `.gitignore` (line 9: `flowstate.json`) excluded the checked-in fixture's state file, so `git add` silently skipped it — the fixture would have been incomplete in the repo.
- **Fix:** Force-added the fixture's flowstate.json (`git add -f`). The other three fixture files are not ignored.
- **Commit:** `3079fa8`

## Honest Caveat (carried in every report header)

Cheap mode validates that the substrate + metrics correctly register compounding signals — it is a regression guard for the measurement apparatus, NOT proof that FlowState causes the LLM to compound. Only `--mode real` tests causation. The convergence axis reads flat under cheap-dry because a dry-run pipeline writes no RUN-journal `artifacts_changed`; the cheap-seed e2e seeds those entries to exercise it.

## Known Stubs

- **`--judge`** is a deliberately unimplemented, guarded spec-only stub (refuses unless `--mode real` + `--allow-llm`; never touches the mechanical score). This is intentional per the plan — Phase B (FeatureBench uplift A/B) is the future surface that would implement real judging.

## Self-Check: PASSED

All created files exist on disk; all four task commit hashes resolve in `git log`.
