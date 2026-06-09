---
phase: 260609-j0g-build-phase-a-intrinsic-compounding-eval
reviewed: 2026-06-09T18:07:11Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - bench/metrics.py
  - bench/capture.py
  - bench/project.py
  - bench/compound_eval.py
  - bench/report.py
  - bench/fixtures/sample_project/
  - tests/test_bench_compound.py
findings:
  blocker: 0
  high: 3
  medium: 4
  low: 4
  total: 11
status: issues_found
---

# Phase 260609-j0g: Code Review Report — bench/ Intrinsic Compounding Harness

**Reviewed:** 2026-06-09T18:07:11Z
**Depth:** deep (cross-file + empirical execution against a fixture copy)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

The `bench/` package is clean on the mechanical-quality axes the constraints demand:
ruff check + format pass, line-length 100 / double quotes / snake_case / `from __future__`
are all honored, imports are stdlib + `rich` + non-bridge `flowstate` only (no banned
third-party deps, no `flowstate.bridge` import), the `_LAYER_HEADINGS` drift guard is
correctly coupled to its real emitters, the `--judge` stub is genuinely inert, the metric
core is well-tested (100% line coverage, no zero-division), and all 32 tests pass. No
`flowstate/` source was modified.

The problems are at the harness-behavior level, and they are serious. The runner executes
`run_pipeline` **in place** against `--root`, so pointing it at the checked-in fixture
pollutes the working tree (HIGH-01). Worse, the fixture ships a stateful `memory.db` that
`scaffold()` never resets, so the harness is **not reproducible run-to-run** — the very
property a "regression guard for the measurement apparatus" exists to provide (HIGH-02).
And two of the four axes (`convergence`, `verify_non_regression`) are **structurally
incapable of firing in cheap mode** because the signals they read are disconnected from the
mutation that is supposed to drive them (HIGH-03). The CAVEAT honestly disclaims causation,
but it does not disclaim that half the scorecard is inert and that the "compounding" verdict
in cheap mode is produced by apparatus artifacts (dedup decay + unreset-memory growth).

Concern checklist results:
1. **No test dirties the checked-in fixture** — all use `tmp_path` or `copytree` to tmp. Clean. (One weak assertion noted as LOW-01.)
2. **never-raises has a hole**: `write_json` / `main` do **not** guard an unwritable `--out` (MEDIUM-01).
3. **Metric correctness is sound** on edge cases (K=1, empty, flat, zero-first); no div-by-zero. One verdict-vs-spec gap noted (LOW-02).
4. **`_LAYER_HEADINGS` guard is correct** — headings map to their true emitters and the test scans the union. Clean.
5. **`--judge` stub is genuinely inert.** Clean.
6. **Caveat prints in every console mode**, but is **absent from the JSON artifact** (MEDIUM-02).

---

## High

### HIGH-01: Runner mutates `--root` in place; in-place run against the checked-in fixture pollutes the repo

**File:** `bench/compound_eval.py:71-89` (`_cheap_loop`), `bench/compound_eval.py:92-105` (`_real_loop`), `bench/project.py:76-116` (`scaffold`)
**Issue:** Both loops run `scaffold(root)` + `run_pipeline(state, root)` directly against the user-supplied `--root`, with no copy-to-scratch. `run_pipeline` writes context files and saves state even in dry-run (orchestrator.py:221 `write_context_files`, :228/:314/:319/:374 `save_state`). Empirically confirmed: running

```
python -m bench.compound_eval --mode cheap --runs 2 --root <copy-of-fixture>
```

produces these files in the root: `.planning/PROJECT.md`, `.planning/ROADMAP.md`,
`.planning/config.json`, `.planning/GOTCHAS.md`, `.planning/RUNLOG.md`, `.claude/CLAUDE.md`,
`.mcp.json`, `research/{brief,report,strategy}.md`, `memory.db`. Against the checked-in
`bench/fixtures/sample_project`, **none of those 8+ output paths are gitignored**
(verified via `git check-ignore`), so they appear as untracked files; and the tracked files
`flowstate.json`, `.planning/fixtures/starter.json`, `.planning/artifacts/work.txt`,
`.planning/phases/01-foundation/01-VERIFICATION.md` are overwritten in place. The README/CLI
help in the module docstring (lines 5, 16) literally instructs the user to run with
`--root bench/fixtures/sample_project` — i.e. the documented invocation dirties the repo.
This is a CI hazard and breaks run-to-run reproducibility.

**Fix:** The runner must never touch the checked-in `--root`. Copy it into a scratch dir and
run the K iterations there:

```python
import shutil
import tempfile

def _cheap_loop(root: Path, runs: int, *, console: Console) -> Scorecard:
    work = Path(tempfile.mkdtemp(prefix="bench_compound_"))
    try:
        shutil.copytree(root, work / "proj", dirs_exist_ok=True)
        target = work / "proj"
        (target / "memory.db").unlink(missing_ok=True)  # see HIGH-02
        scaffold(target)
        # ... loop against `target`, never `root`
    finally:
        shutil.rmtree(work, ignore_errors=True)
```

Alternatively, update the docstring/help to forbid passing the checked-in fixture and have
the runner refuse a `--root` inside the repo tree — but the tempdir approach is the correct
fix.

### HIGH-02: `scaffold()` never resets `memory.db`; harness is not reproducible run-to-run

**File:** `bench/project.py:76-116` (`scaffold` has no `memory.db` reset), `bench/fixtures/sample_project/memory.db` (a 45 KB stateful DB ships in the fixture)
**Issue:** The fixture directory contains a `memory.db` on disk (gitignored, so uncommitted, but physically present). `scaffold()` rewrites `flowstate.json` / fixtures / VERIFICATION but **never deletes or resets `memory.db`**. Every `run_pipeline` invocation appends a new `MemoryKind.RUN` journal entry and re-harvests gotchas into the same DB. Empirically confirmed: two identical `--runs 2` invocations against the same root grew RUN entries 2 → 4. Because `capture_run_snapshot` reads `artifacts_changed` from "the latest RUN entry" and `mem_hits` from a probe search over accumulated memory, **the snapshots — and therefore the verdict — depend on whatever `memory.db` happens to be on disk**, not just on the deterministic scaffold + mutation. This defeats the stated purpose ("a regression guard for the measurement apparatus"): a regression guard that is non-deterministic cannot guard anything. It also means the enrichment axis "grows" partly because memory monotonically accumulates across the loop regardless of any compounding mechanism.

**Fix:** `scaffold()` must reset to a pristine baseline, including the memory store:

```python
def scaffold(root: Path) -> None:
    root = Path(root)
    (root / "memory.db").unlink(missing_ok=True)  # pristine baseline every run
    # ... existing body
```

Combined with HIGH-01's tempdir copy (and dropping the checked-in `memory.db` from the
fixture entirely, since it is gitignored noise), this makes each invocation deterministic.

### HIGH-03: Convergence and verify axes are structurally inert in cheap mode — the cheap scorecard measures only two of four axes

**File:** `bench/project.py:119-136` (`mutate_for_run` mutates `work.txt` but never updates the manifest checksum), `bench/capture.py:122-134` (`artifacts_changed` read), `bench/capture.py:157-168` (verify read)
**Issue:** Empirically running `_cheap_loop(root, 4)` on a fresh fixture yields:

```
run 0: art=0 new_g=5 reenc=0 PFS=0/0/7 tok=764  hits=1 layers=4
run 1: art=0 new_g=0 reenc=5 PFS=0/0/7 tok=886  hits=2 layers=4
run 2: art=0 new_g=0 reenc=5 PFS=0/0/7 tok=1009 hits=3 layers=4
run 3: art=0 new_g=0 reenc=5 PFS=0/0/7 tok=1073 hits=4 layers=4
axes: convergence=flat  gotcha=compounding  verify=flat  enrichment=compounding  → score 2, verdict "compounding"
```

Two root causes:
- **`artifacts_changed` is always 0.** `journal.append_run_entry` (journal.py:46-56) computes
  the delta by diffing `install_manifest` *checksums* against the prior RUN snapshot. But
  `mutate_for_run` rewrites the `work.txt` body (project.py:135-136) **without recomputing
  the manifest checksum** (only `scaffold` ever sets it, project.py:92,107). So the manifest
  checksum is stale relative to the file, the snapshot diff sees no change, and
  `axis_convergence` can never register convergence. The convergence story is wired to a
  signal that the mutation never moves.
- **verify is always 0/0/7 (all skip).** On this fixture `run_verify` returns only skips, so
  `axis_verify_non_regression` is permanently flat. The axis is inert in cheap mode.

Net effect: the cheap "compounding" verdict is produced **entirely** by `gotcha_learning`
(which decays 5→0 purely because gotcha dedup makes run 1+ re-encounters) plus `enrichment`
(which grows partly because `memory.db` accumulates per HIGH-02). The CAVEAT disclaims
causation but does not disclaim that half the scorecard is structurally dead and that the
"compounding" label here is an apparatus artifact. As a regression guard this is misleading:
it will report "compounding" even if convergence/verify detection is completely broken.

**Fix:** Make the convergence signal track the mutation:

```python
# in mutate_for_run, after rewriting work.txt:
new_checksum = hashlib.sha256(body.encode()).hexdigest()[:16]
state = load_state(root)
for entry in state.install_manifest:
    if entry.path == _ARTIFACT_REL:
        entry.checksum = new_checksum
save_state(state, root)
```

For the verify axis, either give the fixture verify gates that actually resolve from
fail→pass across the mutation (so the axis can fire), or document explicitly that cheap mode
only exercises `gotcha_learning` + `enrichment` and exclude the two inert axes from the cheap
score. A scorecard that silently averages two live axes with two dead ones is not honest.

---

## Medium

### MEDIUM-01: `write_json` / `main` violate never-raises on an unwritable `--out`

**File:** `bench/report.py:40-55` (`write_json`), `bench/compound_eval.py:142-144` (`main`)
**Issue:** The runner's docstrings claim never-raises discipline "matching flowstate
verify/journal/gotchas." But `write_json` does `out_path.parent.mkdir(...)` +
`out_path.write_text(...)` with no guard, and `main` calls it unguarded. Confirmed:
`write_json(card, Path("/this/cannot/exist/results.json"))` raises
`OSError: [Errno 30] Read-only file system`, which propagates straight out of `main`. A bad
`--out` (read-only fs, permission denied, path-is-a-directory) crashes the runner with a
traceback instead of degrading gracefully.

**Fix:** Guard the JSON write in `main` and report the failure on the console without raising:

```python
if args.out is not None:
    try:
        write_json(scorecard, Path(args.out))
        console.print(f"[dim]wrote results: {args.out}[/dim]")
    except OSError as exc:
        console.print(f"[red]could not write results to {args.out}: {exc}[/red]")
```

### MEDIUM-02: The honest caveat is absent from the JSON artifact

**File:** `bench/report.py:40-55` (`write_json` payload)
**Issue:** Concern #6 asks whether the caveat reaches every mode. It prints to the console in
all Rich/markdown paths (`render_report` always prints it first, report.py:144) — good. But
the JSON written by `--out` (report.py:42-52) contains `axes`, `compounding_score`,
`verdict`, `snapshots` and **no caveat field**. The JSON file is the artifact most likely to
be archived, diffed into a RUNLOG, or pasted into a PR — i.e. the place a reader is most
likely to mistake the cheap verdict for a causal claim, and it is exactly where the caveat is
missing.

**Fix:** Embed the caveat in the serialized payload:

```python
from bench.report import CAVEAT
payload = {
    "caveat": CAVEAT,
    "mode_note": "cheap mode validates the apparatus, not causation",
    "axes": {...},
    ...
}
```

### MEDIUM-03: Documented run_id-first gotcha attribution is dead in the cheap path

**File:** `bench/capture.py:62-86` (`_is_new_gotcha`), `bench/compound_eval.py:78,84-86` (loop run_id), cross-ref `flowstate/orchestrator.py:176` and `flowstate/gotchas.py` harvest
**Issue:** `capture_run_snapshot`'s primary new-gotcha rule is `entry.run_id == run_id`
(capture.py:69). The cheap loop generates its own `run_id = uuid4().hex[:12]`
(compound_eval.py:78) and passes it to capture. But the gotchas in `memory.db` are written by
`harvest_planning_gotchas` → `capture_gotcha(...)` **without a run_id** (gotchas.py:281-class
call omits `run_id`), so they are stamped `run_id=""`; and `run_pipeline` internally mints a
*different* `run_id` (orchestrator.py:176) for its own journal entry. The bench loop's run_id
therefore **never matches any stored gotcha**, so the run_id-first branch is dead code in
cheap mode and attribution silently falls through to the `window_start` timestamp fallback.
The fallback happens to work (first-seen ≥ window → new on the creating run, re-encounter
after), but the documented primary mechanism (capture.py:108-112) is non-functional and the
discrepancy is invisible. This is a correctness/honesty gap: the code documents a rule it
never actually exercises in the shipped path.

**Fix:** Either (a) thread the bench loop's `run_id` through `run_pipeline`/harvest so stored
gotchas carry it (larger change, touches orchestrator), or (b) drop the run_id-first claim
from the docstrings and document that cheap-mode attribution is window-based, since that is
what actually runs. Given "must not modify flowstate/ source," (b) is the honest minimal fix.

### MEDIUM-04: `_real_loop` is entirely untested and never resets state

**File:** `bench/compound_eval.py:92-105` (`_real_loop`), coverage report shows lines 94-105 uncovered
**Issue:** `_real_loop` has zero test coverage (confirmed: `bench/compound_eval.py 94-105`
missing). It also never calls `scaffold`, so it inherits the HIGH-02 unreset-`memory.db`
problem with no baseline reset at all, and it runs `run_pipeline(..., dry_run=False)` in place
against `--root` (HIGH-01) with no copy. Because it is "research-only, minimal by design," the
absence of a guard or a smoke test means the first real invocation will both dirty `--root`
and produce non-reproducible numbers, with no test to catch a regression in this path.

**Fix:** Apply the HIGH-01 tempdir-copy and HIGH-02 reset to `_real_loop` as well, and add at
least one test that monkeypatches `_run_one` to a no-op and asserts `_real_loop` produces a
`Scorecard` without touching `--root`.

---

## Low

### LOW-01: Smoke test's "fixture untouched" assertion is too weak to catch in-place mutation

**File:** `tests/test_bench_compound.py:579-580`
**Issue:** `test_cheap_dry_smoke_on_fixture_copy` correctly runs against a `copytree` copy, but
its guard against repo pollution is only `assert _FIXTURE_ROOT.exists()` — it checks the
directory still exists, not that its tracked contents are unchanged. If a future refactor
caused the runner to write into `_FIXTURE_ROOT` (the HIGH-01 hazard), this test would still
pass. The assertion gives false confidence.

**Fix:** Snapshot and compare the tracked files, e.g.:

```python
before = (_FIXTURE_ROOT / "flowstate.json").read_text()
... run against the copy ...
assert (_FIXTURE_ROOT / "flowstate.json").read_text() == before
assert not (_FIXTURE_ROOT / ".planning" / "PROJECT.md").exists()
```

### LOW-02: Verdict can be "flat" while an axis is regressing (score-0 masking)

**File:** `bench/metrics.py:152-158`
**Issue:** The verdict is `"regressing"` only when `score < 0`. A scorecard with one
compounding and one regressing axis (plus two flat) nets score 0 → verdict `"flat"`, despite a
genuine regression being present. The spec the task states only defines the `"compounding"`
condition, so this is not a spec violation, but the `"flat"` label understates a real
regression. Low severity because the per-axis fields still expose the `regressing` axis.

**Fix:** Surface regression independent of the net score:

```python
if has_regression and score < 2:
    verdict = "regressing"
elif score >= 2 and enrich == "compounding" and not has_regression:
    verdict = "compounding"
else:
    verdict = "flat"
```

### LOW-03: `project.py` docstring overstates byte-stability of `scaffold`

**File:** `bench/project.py:8` ("idempotent: re-running overwrites in place with byte-stable content")
**Issue:** `scaffold` constructs a fresh `FlowStateModel()` whose `created_at`/`updated_at`
are `datetime.now()` (confirmed: two scaffolds of the same root produce `flowstate.json`
differing on `created_at`, `updated_at`, and a re-ordered `install_manifest`). So
`flowstate.json` is **not** byte-stable across scaffolds — only the fixture JSON and
VERIFICATION are. The `test_scaffold_is_idempotent` test passes only because it compares
`starter.json` and the VERIFICATION file, not `flowstate.json`. The docstring claim is
broader than reality and (per HIGH-01) is the mechanism by which an in-place scaffold dirties
the tracked `flowstate.json`.

**Fix:** Either narrow the docstring ("the fixture and VERIFICATION are byte-stable; state
carries fresh timestamps") or pin deterministic timestamps in the scaffolded state for the
bench target.

### LOW-04: Dead/unused `RunSnapshot` import in the runner

**File:** `bench/compound_eval.py:32`
**Issue:** `from bench.metrics import RunSnapshot, Scorecard, compute_scorecard` — `RunSnapshot`
is used only as a type annotation in the local variables `snapshots: list[RunSnapshot]` and
`prior: RunSnapshot | None` inside the loop bodies, which is legitimate, so this is *not*
actually unused. (Verified ruff passes.) Noting here only to record that I checked: no dead
imports exist in `bench/`. **No action required.** Retained as an explicit "clean" marker per
review instructions.

---

## What is clean (explicitly verified)

- **ruff check + ruff format**: pass on all 7 files (line-length 100, double quotes, snake_case, `from __future__ import annotations` present everywhere).
- **No banned deps / no bridge import**: imports are stdlib + `rich` + non-bridge `flowstate` only; `grep` for `flowstate.bridge` returns nothing.
- **No `flowstate/` source modified**: diff is additive (`bench/` + one test file).
- **`_LAYER_HEADINGS` drift guard (concern #4)**: correct. The four headings map to their true emitters — `## Prior Knowledge` from `memory.py:311`, the other three from `context_prefix.py:215/239/261`; the pack layer is correctly treated as headerless. `test_layer_headings_match_context_prefix_source` scans the union of both emitter files. Sound.
- **`--judge` stub (concern #5)**: genuinely inert. Refuses unless `--mode real` AND `--allow-llm`; even when "considered" it only prints a notice; never calls a bridge/LLM; never feeds the mechanical score. Tests cover refusal and flag-absent no-op.
- **Metric correctness (concern #3)**: K=1/empty/single → all-flat, score 0 (tested); flat sequences → flat on every axis (tested); no division by zero (tolerance band is multiplicative `abs(first)*0.10`, and `first=0` degrades to a strict `<`/`>` comparison, which is correct for non-negative counts); score clamped to [-4,+4]; `compounding` verdict gate (score ≥ 2 AND enrichment compounding AND no regression) matches the stated spec and is exercised by `test_verdict_requires_enrichment_compounding` (meaningful: score 3, enrichment flat → verdict flat).
- **Tests pass**: 32/32; `bench/` package line coverage 89% (metrics/project/report at 100%).
- **No test dirties the checked-in fixture (concern #1)**: every `scaffold`/`mutate`/`main` call targets `tmp_path` or a `copytree` copy.

---

_Reviewed: 2026-06-09T18:07:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
