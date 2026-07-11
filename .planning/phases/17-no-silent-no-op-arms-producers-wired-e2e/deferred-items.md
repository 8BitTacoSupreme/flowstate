# Deferred Items — Phase 17

Out-of-scope discoveries logged during plan execution (not fixed, per SCOPE BOUNDARY).

## 17-02

- **`tests/test_bench_distiller.py` imports a non-existent `bench.distiller` module.**
  Found during: full-suite verification for 17-02.
  Both files (`bench/distiller.py`, `tests/test_bench_distiller.py`) are untracked
  in this worktree and predate 17-02's execution — not part of this plan's
  `files_modified` (`bench/compound_eval.py`, `tests/test_bench_compound.py`).
  `bench/distiller.py` is absent from the worktree filesystem while the test
  file that imports it remains, breaking `pytest -q` full-suite collection
  (`ModuleNotFoundError: No module named 'bench.distiller'`). Verification for
  this plan was run with `--ignore=tests/test_bench_distiller.py` to route
  around it: 1059 passed, 91.07% coverage. Whichever plan owns `bench/distiller.py`
  (likely a sibling wave plan) should confirm it lands the module or removes the
  orphaned test file.
