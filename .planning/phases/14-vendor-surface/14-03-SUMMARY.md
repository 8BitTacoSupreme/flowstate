---
phase: 14-vendor-surface
plan: 03
subsystem: installer
status: complete
tags: [installer, vend-03, skills, path-safety, idempotent, tdd]
requires: [VEND-03]
provides:
  - "flowstate install-skills copies vendored gstack+superpowers into .claude/skills/"
  - "init and kickoff auto-install skills (init respects --dry-run)"
  - "reusable _NAMESPACES-driven installer extensible for Phase 15 (GSD)"
affects: [flowstate/installer.py, flowstate/cli.py, tests/test_installer.py]
tech-stack:
  added: []
  patterns:
    - "stdlib shutil.copytree(dirs_exist_ok, symlinks=False) + ignore-symlinks callback"
    - "dir-level InstallEntry manifest tracking (kind=artifact, checksum=None) mirroring context._register idempotence"
    - "explicit (source_subdir, dest_namespace) pair list for extensibility"
key-files:
  created:
    - flowstate/installer.py
    - tests/test_installer.py
  modified:
    - flowstate/cli.py
decisions:
  - "Reused kind=artifact for skill manifest entries — no state.py schema migration (per plan interface note)"
  - "Dir-level manifest entries (not per-file) so fresh's shutil.rmtree cleans namespaces correctly and checksum=None avoids sha256-of-dir failure"
  - "Symlinks skipped via copytree ignore callback (belt-and-suspenders with symlinks=False) — never followed out of tree"
  - "Path-safety guard asserts each resolved dest is inside root/.claude/skills before any write"
metrics:
  duration: ~3 min
  completed: 2026-07-10
requirements: [VEND-03]
---

# Phase 14 Plan 03: flowstate install-skills Installer (VEND-03) Summary

Built `flowstate/installer.py` — a pure-Python (`shutil`) installer that copies the vendored `flowstate/skills/{gstack,superpowers}` trees into a project's `.claude/skills/`, wired it as a first-class `flowstate install-skills` command and auto-invoked it from `init` and `kickoff`, so a fresh project needs zero manual skill install. Idempotent, path-safe, dry-run-safe, manifest-tracked, and structured (an explicit `_NAMESPACES` pair list) so Phase 15 adds GSD without rewriting the copy logic.

## What Shipped

**Task 1 — installer.py (TDD; test commit `fc2c3e4`, feat commit `7f7884d`):**
- `install_skills(root, *, dry_run=False, state=None) -> list[Path]` resolves the vendored source at `Path(flowstate.__file__).parent / "skills"` and drives the copy from `_NAMESPACES = [("gstack","gstack"), ("superpowers","superpowers")]`.
- `_copy_tree` uses `shutil.copytree(dirs_exist_ok=True, symlinks=False)` with an `ignore` callback that drops any symlink in the source — a source symlink is never materialized or followed (T-14-08, T-14-11: data-only copy).
- Path-safety: each resolved destination is asserted inside `(root/.claude/skills).resolve()` before writing; overwrites are scoped to the two vendored namespaces only, so a pre-existing `.claude/skills/mine/custom.md` survives untouched (T-14-07, T-14-09).
- `dry_run=True` performs zero writes and no state save, returning the would-be namespace paths (T-14-10).
- When `state` is passed (and not dry-run), records one dir-level `InstallEntry` per namespace (`path=.claude/skills/{ns}`, `owner="skills"`, `kind="artifact"`, `checksum=None`), idempotently replacing any prior entry — mirrors `context._register`. Reused `kind="artifact"` → **no state.py migration**.

**Task 2 — CLI command + init/kickoff wiring (commit `01bad7e`):**
- New `@main.command("install-skills")` with `--root`/`--dry-run`; loads state, installs, saves (unless dry-run), prints installed namespaces via Rich (mirrors the `context` command's output style).
- `init`: calls `install_skills(root, dry_run=state.preferences.dry_run, state=state)` after `run_pipeline` and before the final `save_state` — respects `--dry-run`.
- `kickoff`: calls `install_skills(root, dry_run=False, state=state)` after `write_context_files` and before the final `save_state` (kickoff has no dry-run).

## Tests

`tests/test_installer.py` — 10 offline temp-dir tests: both-namespace copy, returned-paths shape, idempotence, no-clobber of user skills, dry-run-writes-nothing, dry-run-skips-manifest, manifest records both namespaces (artifact/skills/None), manifest idempotent on reinstall, source-symlink-skipped (via a monkeypatched fake source tree with an escaping symlink), destination-confined-to-skills-dir.

## Verification

- `python -m pytest tests/test_installer.py -q` → 10 passed.
- `flowstate install-skills --root <tmp>` exits 0, creates `.claude/skills/gstack/office-hours/SKILL.md`; `--dry-run` creates no `.claude/`.
- `grep -c install_skills flowstate/cli.py` → 7 (init + kickoff + command + imports).
- Full suite `python -m pytest -q` → **995 passed, 91.74% coverage** (≥80%). installer.py module coverage 94% (uncovered lines are the defensive not-a-dir `continue` and the path-safety `raise`).

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: flowstate/installer.py
- FOUND: tests/test_installer.py
- FOUND: flowstate/cli.py (modified)
- FOUND commit: fc2c3e4 (test RED)
- FOUND commit: 7f7884d (feat GREEN — installer)
- FOUND commit: 01bad7e (feat — CLI + init/kickoff)
