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
