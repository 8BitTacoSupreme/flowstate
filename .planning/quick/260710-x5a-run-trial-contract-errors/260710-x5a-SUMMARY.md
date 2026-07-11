---
phase: 260710-x5a
plan: 01
type: tdd
status: complete
subsystem: bench
tags: [replicate, error-handling, contract-violation, judge, tdd]
dependency_graph:
  requires: [bench/replicate.py]
  provides: []
  affects: [bench/close_loop.py]
tech_stack:
  added: []
  patterns: [narrow-except-over-broad-except, fail-fast-on-contract-violation, subprocess.CompletedProcess fake in tests]
key_files:
  created: []
  modified:
    - bench/replicate.py
    - tests/test_bench_replicate.py
decisions:
  - "Strict mode (per approved plan): judge-output contract violations (malformed JSON, missing 'score' key) propagate uncaught from _run_trial instead of collapsing to None, so bench/close_loop.py's existing pipeline except-Exception guard surfaces them as exit 1 instead of the CI silently averaging them out as a trial gap"
  - "Single try/except OSError/finally retained (not nested) — subprocess.run(check=False) never raises on nonzero returncode, so the returncode check lives inside the same try as the file read; json.loads + score extraction moved after the finally so only that stage's exceptions propagate"
  - "Existing fd/tempfile-cleanup regression tests updated to return subprocess.CompletedProcess(cmd, returncode=...) from their fake_run — required because _run_trial now reads proc.returncode, which the old None-returning fakes didn't provide"
  - "Missing-output-file test explicitly unlinks the mkstemp-created file inside the fake (rather than 'writing nothing') because mkstemp always pre-creates the file, so an empty file previously parsed to a JSONDecodeError contract violation, not an OSError gap"
metrics:
  duration_minutes: 20
  completed: "2026-07-11T03:58:39Z"
  tasks_completed: 2
  files_modified: 2
  tests_added: 5
  coverage_after: 90.00
---

# Phase 260710-x5a Plan 01: Harden `_run_trial` Error Handling Summary

Reworked `bench/replicate.py::_run_trial` to distinguish three failure classes instead of collapsing them under one bare `except Exception: return None`: harness gaps (nonzero subprocess returncode) and output gaps (unreadable/missing file, `OSError`) still return `None` with a printed diagnostic, while judge-output contract violations (malformed JSON, a `per_run` row missing its `score` key) now propagate uncaught so they can't be silently averaged into the paired-bootstrap CI as if they were harmless trial gaps.

## What Was Built

### `bench/replicate.py::_run_trial` (reworked)

- `proc = subprocess.run(cmd, check=False)`; nonzero `proc.returncode` prints
  `[replicate] {label}: compound_eval exited {rc}` (flush=True) and returns `None`.
- The output-file read (`out.read_text()`) sits inside the same `try` and is caught by
  `except OSError as exc:`, printing `[replicate] {label}: no/unreadable output ({exc})`
  (flush=True) and returning `None`. The broad `except Exception` is gone.
- `finally: out.unlink(missing_ok=True)` (and the `os.close(fd)` right after `mkstemp`)
  are unchanged — the fd-leak/tempfile-litter fix from the Phase-18 WR-02 work is preserved.
- `json.loads(raw)` and `scores = [r["score"] for r in ...]` moved to **after** the
  try/finally block, so `json.JSONDecodeError` / `KeyError` / `TypeError` propagate to
  the caller instead of being swallowed.
- The final guard `if not scores or any(s is None for s in scores): return None` and
  `return [float(s) for s in scores]` are unchanged.
- Docstring rewritten to document the three-class contract.

`bench/close_loop.py` is **unchanged** (confirmed via `git diff --stat` returning empty
both mid-execution and at final verification) — its existing `except Exception as exc:  #
never raise` pipeline guard around the call site already turns a propagated contract
violation into a reported non-zero exit rather than a crash, with no code change needed.

### `tests/test_bench_replicate.py`

Two pre-existing fd/tempfile-cleanup tests (`test_run_trial_removes_temp_file_on_success`,
`test_run_trial_removes_temp_file_on_failure`) were updated in the same commit as the
`_run_trial` rework, because their `fake_run` helpers previously returned `None` (no
`.returncode` attribute) — `_run_trial` now reads `proc.returncode`, so those fakes needed
to return `subprocess.CompletedProcess(cmd, returncode=0)`. The failure-case fake was also
changed from "write nothing to `--out`" to "unlink the mkstemp-created file", since
`mkstemp` always pre-creates the file — writing nothing left an empty (not missing) file,
which under the new contract parses to a `JSONDecodeError` (contract violation) rather than
triggering the `OSError` gap path the test intended to exercise.

Five new regression tests were added covering the full three-class contract:

1. `test_run_trial_raises_on_malformed_json` — non-JSON content in `--out`, returncode 0 →
   `pytest.raises(json.JSONDecodeError)`.
2. `test_run_trial_raises_on_missing_score_key` — valid JSON but a `per_run` row without
   `score` → `pytest.raises(KeyError)`.
3. `test_run_trial_returns_none_on_nonzero_returncode` — returncode 1 → `None`, diagnostic
   `"compound_eval exited 1"` printed, temp file unlinked.
4. `test_run_trial_returns_none_on_missing_output_file` — fake deletes the mkstemp file →
   `None`, diagnostic `"no/unreadable output"` printed.
5. `test_run_trial_happy_path_returns_float_scores` — valid payload, returncode 0 →
   `[7.0, 9.0]`, temp file unlinked (regression guard).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing fd/tempfile-cleanup tests broken by the returncode contract change**
- **Found during:** Task 1 verification (`uv run python -m pytest tests/test_bench_replicate.py -q`)
- **Issue:** `test_run_trial_removes_temp_file_on_success` and `..._on_failure` monkeypatched
  `subprocess.run` with fakes returning `None`; `_run_trial` now dereferences
  `proc.returncode`, so both raised `AttributeError` instead of exercising the intended path.
  The failure-case fake additionally relied on "write nothing" to trigger a missing-file
  OSError, which no longer holds once `mkstemp` pre-creates an empty file (empty content
  parses to a `JSONDecodeError`, a contract violation, not an `OSError` gap).
- **Fix:** Updated both fakes to return `subprocess.CompletedProcess(cmd, returncode=0)`;
  changed the failure-case fake to `Path(out_path).unlink()` to genuinely simulate a missing
  output file.
- **Files modified:** `tests/test_bench_replicate.py`
- **Commit:** `ba21455`

No architectural changes; no auth gates encountered.

## Verification

- `uv run python -m pytest tests/test_bench_replicate.py -q` — 25 passed (20 pre-existing + 5 new).
- `uv run python -m pytest tests/ --cov=flowstate --cov=bench --cov-fail-under=80 -q` — 1107 passed, total coverage 90.00%.
- `uv run ruff check flowstate/ bench/ tests/` — All checks passed.
- `git diff --stat bench/close_loop.py` — empty (unchanged).
- `git diff --stat uv.lock pyproject.toml` — empty at commit time (an ephemeral `uv run`-induced
  `uv.lock` rewrite was reverted with `git checkout -- uv.lock` before each commit, per the
  environment note; neither file is part of either commit).

## Commits

- `ba21455` — `feat(260710-x5a): separate trial gaps from contract violations in _run_trial`
- `a689922` — `test(260710-x5a): lock the _run_trial three-class error contract`

## Self-Check: PASSED

- FOUND: `bench/replicate.py` (modified, contains `except OSError`, no bare `except Exception`)
- FOUND: `tests/test_bench_replicate.py` (25 tests, includes the 5 new cases)
- FOUND commit `ba21455` in `git log --oneline`
- FOUND commit `a689922` in `git log --oneline`
- CONFIRMED: `bench/close_loop.py` has an empty git diff
