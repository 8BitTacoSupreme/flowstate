# Deferred Items — Phase 25

## test_installer_gsd.py::test_gsd_sdk_full_parity_query fails in worktree (pre-existing, out of scope)

**Found during:** 25-01 full-suite regression check (`pytest -q --no-cov`).
**Symptom:** `node` MODULE_NOT_FOUND against `.claude/get-shit-done/node_modules/bin/gsd-sdk.js`.
**Root cause:** `.claude/get-shit-done/node_modules` is untracked (0 files under git per
`git ls-files`), so it does not exist in a fresh git-worktree checkout — it only exists in
the main checkout where `flowstate.gsd_vendor.refresh()` was run manually at some point.
**Scope:** Unrelated to 25-01's changes (`flowstate/sandbox.py`, `flowstate/gsd_vendor.py`
comment-only edits, `tests/test_sandbox.py`). Not fixed — out of scope per the executor's
scope-boundary rule. Confirmed 101/101 tests pass in `tests/test_sandbox.py` +
`tests/test_gsd_vendor.py`; only this one unrelated test fails in the full suite
(1319 passed, 1 skipped, 1 failed).

## test_verdict.py::test_real_mode_no_paired_data_fails_loud fails in worktree (pre-existing, out of scope)

**Found during:** 25-04 full-suite regression check (`pytest tests/ -q`, run to confirm the
`build_linux_bwrap_args` `--tmpfs /tmp` fix didn't regress anything project-wide).
**Symptom:** `RuntimeError` (paired-data assertion) unrelated to sandbox/bwrap-argv
plumbing — a `flowstate/verify.py`/bench-harness concern, not touched by this plan.
**Scope:** Unrelated to 25-04's changes (`flowstate/sandbox.py::build_linux_bwrap_args`,
`tests/test_sandbox.py` golden-test update, `25-SPIKE-LINUX-REPROBE.md`). Not fixed — out
of scope per the executor's scope-boundary rule. `tests/test_sandbox.py` is 73/73 green;
only this one unrelated test (plus the already-documented `test_installer_gsd.py` one
above) fails in the full suite (1327 passed, 1 skipped, 2 failed).
