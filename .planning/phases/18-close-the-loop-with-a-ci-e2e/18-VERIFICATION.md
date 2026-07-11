---
phase: 18-close-the-loop-with-a-ci-e2e
verified: 2026-07-11T02:50:42Z
status: passed
score: 12/12 must-haves verified
overrides_applied: 0
---

# Phase 18: Close the Loop with a CI + E2E Verification Report

**Phase Goal:** Multi-sample judging + paired-bootstrap CI wired into compound_eval's Track-2 path (reusing grounding.py/replicate.py); one command runs prior-runs→distill→inject→judge and returns a CI'd delta; a green E2E smoke test exercises every arm's plumbing and asserts fail-loud on a missing producer.
**Verified:** 2026-07-11T02:50:42Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A seeded paired-bootstrap 95% CI can be computed on per-trial judge deltas with pure stdlib (no new deps) | VERIFIED | `bench/bootstrap.py` imports only `random`, `statistics` (grep confirmed). `_BOOTSTRAP_SEED = 1729` named constant present (grep count 2). |
| 2 | Re-running the bootstrap with the same inputs/seed yields byte-identical CI bounds | VERIFIED | Ran `paired_bootstrap_ci(deltas)` twice live: `{'n': 7, 'mean': 0.81, 'ci_low': -0.16, 'ci_high': 1.84, ...}` both calls — `IDENTICAL`. `tests/test_bench_bootstrap.py::test_same_seed_returns_identical_dicts` also asserts this. |
| 3 | replicate.py's Track-2 output carries a paired-bootstrap CI'd delta for each arm vs the none baseline | VERIFIED | `bench/replicate.py` lines 182-194: builds `paired_deltas` from `arms_summary[arm][metric]['improvements']` vs `none`'s, calls `paired_bootstrap_ci`, stores `summary["bootstrap_ci_delta_vs_none"]`. Test `test_main_emits_bootstrap_ci_delta_vs_none` passes. |
| 4 | The judge/CI output stays Track-2 and is never fed into metrics.py's deterministic compounding_score | VERIFIED | `grep -n "import.*metrics\|compute_scorecard" bench/replicate.py bench/close_loop.py` returns nothing. `git diff --name-only bench/report.py` shows no phase-18 commits touched it (last touch was pre-phase commit f79435b). |
| 5 | One command runs prior-runs → distill → inject → judge on a fixture end-to-end and returns a CI'd delta, not a single-shot score | VERIFIED | Ran `uv run python -m bench.close_loop --root bench/fixtures/sample_project --mode cheap --trials 3 --runs 3` live — exit 0, JSON with `bootstrap_ci_delta_vs_baseline` (mean/ci_low/ci_high/n/resamples/seed/confidence). |
| 6 | The command has a cheap/deterministic mode that runs with NO live LLM/bridge (CI-safe) | VERIFIED | Live run above required no `claude` binary. `_cheap_trajectories` uses `random.Random(seed)` only, no subprocess import in close_loop.py. |
| 7 | The distill step runs in an isolated, scaffold-seeded worktree copy of --root so the checked-in fixture is never mutated | VERIFIED | Post-run check: `git status --porcelain bench/fixtures/sample_project` empty; `memory.db` and `.planning/codebase/wiki` absent from the checked-in fixture. `close_loop.py` wraps pipeline in `with _worktree(root) as target:` and calls `scaffold(target)` before `prepare_fixture.main`. |
| 8 | The distill step reuses bench.prepare_fixture/bench.distiller; the judge step reuses bench.replicate; the CI reuses bench.bootstrap — nothing is rebuilt | VERIFIED | `close_loop.py` imports `bench.prepare_fixture`, `bench.replicate` (`_run_trial`, `_agg`), `bench.bootstrap.paired_bootstrap_ci`, `bench.compound_eval._worktree`, `bench.project.scaffold`. Grep count for reuse-target names >= 3 (actual: 13). |
| 9 | The CI'd delta is Track-2 output and never touches the deterministic compounding_score | VERIFIED | Same grep as truth 4 — no metrics import in close_loop.py; JSON `note` field explicitly states "EXCLUDED from compounding_score". |
| 10 | A green, CI-safe E2E smoke test exercises every arm's plumbing (none/pack/memory/wiki/full) with no live LLM/bridge and no network | VERIFIED | `tests/test_bench_e2e_smoke.py` — all 4 tests pass under plain pytest; `test_every_arm_covered` asserts tested-arm union equals `compound_eval._ARM_PRODUCERS` (the drift guard). |
| 11 | The smoke test asserts the harness fails loud (exit 3) when an arm's required producer artifact is absent | VERIFIED | `test_producer_arms_fail_loud_when_absent` asserts `rc == compound_eval._EXIT_PRODUCER_ABSENT` (symbolic, not literal 3) — grep count 4 in file. |
| 12 | The smoke test asserts each producer-less arm and each producer-satisfied arm returns 0 in cheap mode | VERIFIED | `test_producerless_arms_run_green` and `test_producer_arms_run_green_when_present` both assert `== 0` for the respective arm sets. |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bench/bootstrap.py` | `paired_bootstrap_ci` stdlib helper + `_BOOTSTRAP_SEED` constant | VERIFIED | Exists, substantive (98 lines, full docstring, never-raises try/except), stdlib-only imports confirmed. |
| `tests/test_bench_bootstrap.py` | determinism + edge-case coverage | VERIFIED | 10 tests: same-seed identity, default-seed-is-named-constant, empty input, n==1 degenerate, all-equal, mixed-sign bracket, seed-changes-bounds, non-numeric never-raises, key presence. |
| `bench/close_loop.py` | the one-command driver, `def main` | VERIFIED | 175 lines, `main(argv=None) -> int`, argparse with `--root/--arm/--baseline/--trials/--runs/--mode/--seed/--out`, wired to `_worktree`/`scaffold`/`prepare_fixture`/`replicate`/`paired_bootstrap_ci`. Live-run confirmed exit 0 with correct JSON shape. |
| `tests/test_bench_close_loop.py` | CI-safe E2E test asserting CI'd delta + fixture unmutated | VERIFIED | 4 tests: cheap-mode CI delta, non-mutation, determinism (same seed), real-mode plumbing via monkeypatched `_run_trial`/`prepare_fixture.main` (no subprocess). |
| `tests/test_bench_e2e_smoke.py` | "harness of harnesses works E2E" acceptance gate | VERIFIED | 4 tests covering producerless-green, producer-absent-fail-loud, producer-present-green, and arm-vocabulary drift guard. All pass under plain pytest, no `claude` binary. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `bench/replicate.py` | `bench/bootstrap.py` | `paired_bootstrap_ci` on per-trial improvement deltas vs none | WIRED | `from bench.bootstrap import paired_bootstrap_ci` (line 28); called at line 193 inside the `if "none" in arms_summary:` block. |
| `bench/replicate.py` | `bench/metrics.py` | must NEVER import metrics/compute_scorecard | WIRED (isolation held) | grep confirms zero matches. |
| `bench/close_loop.py` | `bench/compound_eval.py` | `_worktree` isolation + `bench.project.scaffold` seeding before distill | WIRED | `from bench.compound_eval import _worktree` (line 36); `with _worktree(root) as target:` at line 132; `scaffold(target)` called first inside `_distill()`. |
| `bench/close_loop.py` | `bench/prepare_fixture.py` | distill/inject-prep step on the seeded worktree | WIRED | `import bench.prepare_fixture as prepare_fixture` (line 33); `prepare_fixture.main([...])` called in `_distill()` only for producer arms (pack/wiki). |
| `bench/close_loop.py` | `bench/bootstrap.py` | `paired_bootstrap_ci` on the per-trial judge deltas | WIRED | `from bench.bootstrap import _BOOTSTRAP_SEED, paired_bootstrap_ci` (line 35); called at line 149. |
| `tests/test_bench_e2e_smoke.py` | `bench.compound_eval.main` | cheap-mode per-arm invocation + `_EXIT_PRODUCER_ABSENT` assertion | WIRED | `_run()` helper calls `compound_eval.main([...])`; `_EXIT_PRODUCER_ABSENT` referenced symbolically (grep count 4). |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Bootstrap determinism (live, outside pytest) | `paired_bootstrap_ci(deltas)` called twice in a fresh `uv run python -c` process | Identical dicts (`{'n': 7, 'mean': 0.81, 'ci_low': -0.16, 'ci_high': 1.84, ...}` both times) | PASS |
| One-command close_loop exits 0 with CI'd delta | `uv run python -m bench.close_loop --root bench/fixtures/sample_project --mode cheap --trials 3 --runs 3` | Exit 0; JSON with `bootstrap_ci_delta_vs_baseline` populated | PASS |
| Fixture non-mutation | `git status --porcelain bench/fixtures/sample_project` after the close_loop run; `test ! -e .../memory.db`; `test ! -e .../.planning/codebase/wiki` | Empty status; both paths absent | PASS |
| ruff clean | `uv run ruff check flowstate/ bench/ tests/` | "All checks passed!" | PASS |
| Full suite green + coverage | `uv run python -m pytest tests/ --cov=flowstate --cov=bench --cov-fail-under=80 -q` | 1096 passed, coverage 89.81% | PASS |
| Phase-18 test subset green | `uv run python -m pytest tests/test_bench_bootstrap.py tests/test_bench_replicate.py tests/test_bench_close_loop.py tests/test_bench_e2e_smoke.py -q` | 33 passed | PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` convention; verification was done via direct pytest/CLI execution per the phase's own `<verify><automated>` blocks, all of which were independently re-run above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| HAR-04 | 18-01, 18-02 | Wire multi-sample judging + paired-bootstrap CI into Track-2; one command runs prior-runs→distill→inject→judge and returns a CI'd delta | SATISFIED | `bench/bootstrap.py` + `bench/replicate.py` wiring (18-01); `bench/close_loop.py` one-command driver (18-02); live-run verified. |
| HAR-05 | 18-03 | Green E2E smoke test exercises every arm's plumbing and asserts fail-loud on missing producer | SATISFIED | `tests/test_bench_e2e_smoke.py`, 4/4 tests green, `_EXIT_PRODUCER_ABSENT` used symbolically, `_ARM_PRODUCERS` drift guard present. |

No orphaned requirements — REQUIREMENTS.md traceability table maps both HAR-04 and HAR-05 exclusively to Phase 18, and both are claimed across the three plans' frontmatter.

### Anti-Patterns Found

None. Scanned `bench/bootstrap.py`, `bench/close_loop.py`, `bench/replicate.py`, and all three new test files for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|placeholder|not yet implemented|coming soon` — zero matches.

### Human Verification Required

None. All must-haves are programmatically verifiable and were independently re-executed (not just read from SUMMARY claims).

### Gaps Summary

No gaps. All 12 derived truths verified against live command execution, all 5 required artifacts exist/substantive/wired, all 6 key links wired, full test suite green (1096 passed) with 89.81% coverage, ruff clean, no anti-patterns, no orphaned requirements. The one-command `bench.close_loop` was independently invoked (not trusted from SUMMARY) and confirmed to exit 0, emit a CI'd delta, and leave the checked-in fixture byte-for-byte unmutated (`git status --porcelain` empty pre/post).

Note: `uv.lock` showed a spurious modification (unrelated dependency-resolution churn, likely from environment `uv run` auto-sync) both before and after test execution in this verification session; it was reverted via `git checkout -- uv.lock` each time per the environment note, and is unrelated to phase 18's own file set (`bench/bootstrap.py`, `bench/close_loop.py`, `bench/replicate.py`, three test files) which show as clean/committed.

---

_Verified: 2026-07-11T02:50:42Z_
_Verifier: Claude (gsd-verifier)_
