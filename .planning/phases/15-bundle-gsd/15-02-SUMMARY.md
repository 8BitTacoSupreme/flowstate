---
phase: 15-bundle-gsd
plan: 02
subsystem: installer
status: complete
tags: [installer, gsd, packaging, skills, unconditional-install]
requires:
  - flowstate/vendor/gsd (15-01 — the vendored full-parity GSD distribution)
provides:
  - flowstate.installer.install_gsd (lays down runtime + node_modules + gsd-* skills)
  - install_skills now installs GSD unconditionally for every caller (init/kickoff/CLI)
affects:
  - 15-03 (launcher delegates to the installed gsd-sdk)
  - 15-04 (refresh path re-runs the same install)
tech-stack:
  added: []
  patterns: [copy-as-data, unconditional-install, per-command-skill-conversion, path-prefix-rewrite]
key-files:
  created:
    - tests/test_installer_gsd.py
  modified:
    - flowstate/installer.py
    - tests/test_installer.py
decisions:
  - "GSD installs UNCONDITIONALLY through install_skills (no detect gate, no prompt) so init/kickoff/CLI all lay it down with zero CLI change."
  - "Full node_modules copied to .claude/get-shit-done/node_modules/ so gsd-sdk resolves its deps by walking up — byte-identical to the tree 15-01 proved invokable; no PATH symlink, no shim."
  - "commands/gsd/*.md converted to .claude/skills/gsd-<cmd>/SKILL.md via a minimal faithful port of get-shit-done-cc's convertClaudeCommandToClaudeSkill (canonical hyphen name + local path-prefix rewrite), NOT a verbatim _copy_tree — the flat dir copy could not produce gsd-* skill dirs."
metrics:
  duration: ~20 min
  completed: 2026-07-10
---

# Phase 15 Plan 02: Install Vendored GSD Unconditionally Summary

`flowstate install-skills` (and its `init`/`kickoff` callers) now lays down the full vendored GSD distribution with no detect gate and no prompt: the `get-shit-done` runtime, the complete `node_modules` (so `node <installed>/gsd-sdk.js` runs with full parity), and every `commands/gsd/*.md` converted into a canonical `.claude/skills/gsd-<cmd>/SKILL.md` — path-safe, idempotent, dry-run-safe, and manifest-tracked, with no `gsd-tools.cjs` shim.

## What Was Built

**Task 1 + 2 — GSD install path + fresh-project proof (commit `0534d0e`)**

`flowstate/installer.py` gains `install_gsd(root, *, dry_run, state)`, wired into `install_skills` so every existing caller surfaces GSD with zero CLI change. Three destinations:

1. `node_modules/get-shit-done-cc/get-shit-done` → `.claude/get-shit-done/` (the runtime skills reference)
2. `flowstate/vendor/gsd/node_modules` → `.claude/get-shit-done/node_modules/` — the full tree (get-shit-done-cc + ~90 deps). `bin/gsd-sdk.js` → `sdk/dist/cli.js` resolves `@anthropic-ai/claude-agent-sdk` + `ws` by walking up to this `node_modules`, byte-identical to the layout 15-01 proved invokable.
3. `commands/gsd/*.md` → `.claude/skills/gsd-<cmd>/SKILL.md`, each converted by `_command_to_skill` (frontmatter rebuilt with the canonical hyphen `name: gsd-<cmd>`, preserving description/argument-hint/agent/allowed-tools) after `_apply_path_prefix` rewrites `$HOME/.claude/` and `~/.claude/` to the project-local runtime — a minimal faithful port of get-shit-done-cc's `convertClaudeCommandToClaudeSkill`.

Reused Phase-14 mechanics: `_copy_tree` (symlink-skipping, `dirs_exist_ok`) for the two tree copies, `_register` for the manifest (extended with an `owner` arg, `owner="gsd"`), and a generalized `_assert_within(claude_root, dest)` path-traversal guard applied to every GSD destination. The install is unconditional — no `if gsd_present` branch. Vendored code is copied as DATA; the installer never spawns a subprocess.

## Invokability Gate (confirmed this plan)

`tests/test_installer_gsd.py::test_gsd_sdk_full_parity_query` (node present, not skipped) installs into a fresh temp project, seeds a minimal `.planning/ROADMAP.md`, and runs:

```
node <tmp>/.claude/get-shit-done/node_modules/get-shit-done-cc/bin/gsd-sdk.js query roadmap.get-phase 1
```

→ exit 0, stdout contains `Bundle GSD`. Full parity from the *installed* tree confirmed; the authoritative proof remains 15-01's recorded exit-0.

## Tests

`tests/test_installer_gsd.py` (14 tests, all green): fresh-project layout (runtime + `gsd-*` skills + `gsd-sdk` + co-located `@anthropic-ai/claude-agent-sdk`/`ws`), unconditional install, hyphenated skill frontmatter, idempotence (tree + manifest), dry-run (writes nothing, returns dests, no manifest touch), path-traversal refusal, no-clobber of user skills, copy-not-execute (trips `subprocess.run`/`Popen`/`os.system`), and the node-gated parity query.

Full suite: **1014 passed, 91.79% coverage** (installer.py at 92%); ≥80% gate held.

## Deviations from Plan

### Auto-fixed / adjusted

**1. [Rule 3 - Blocking] Skill conversion needed, not a verbatim `_copy_tree`**
- **Found during:** Task 1 — reading the vendored `install.js` (`copyCommandsAsClaudeSkills`).
- **Issue:** The plan suggested folding the skills mapping into a `_copy_tree`-based `(source, dest)` list, but a flat directory copy of `commands/gsd/` produces `.claude/skills/add-tests.md`, not the required `gsd-*` skill dirs. GSD's own installer transforms each command `.md` into `gsd-<cmd>/SKILL.md` with a rewritten `name`.
- **Fix:** Kept `_copy_tree` + `_GSD_TREE_MAPPINGS` for the two whole-tree copies (runtime, node_modules) and added a small faithful port of `convertClaudeCommandToClaudeSkill` for the skills. Load-bearing behavior (canonical hyphen name, preserved tool grants, project-local path prefix) reproduced; cosmetic `processAttribution` git-comment injection omitted (non-functional).
- **Files modified:** `flowstate/installer.py`
- **Commit:** `0534d0e`

**2. [Rule 3 - Blocking] Rescoped four Phase-14 `test_installer.py` assertions**
- **Found during:** Task 1 — the `install_skills` return contract and write surface changed by design (plan: "Fold the GSD destinations into the install_skills return list").
- **Issue:** Existing tests asserted the return set was *exactly* `{gstack, superpowers}`, that *every* manifest entry had `owner="skills"`, that exactly two entries started with `.claude/skills/`, and that all writes stayed under `.claude/skills`. All now legitimately false (GSD adds dests, `owner="gsd"` entries, `gsd-*` skill dirs, and `.claude/get-shit-done` writes).
- **Fix:** Rescoped to subset/`owner`-filtered assertions and widened the confinement test to `.claude` (renamed `test_destination_confined_to_claude_dir`). No production behavior weakened — the vendored-skills namespaces are still asserted exactly.
- **Files modified:** `tests/test_installer.py`
- **Commit:** `0534d0e`

**3. [Process] Tasks 1 and 2 committed together**
- Task 2 adds only functional proof tests to the same `tests/test_installer_gsd.py` authored as the TDD spec for Task 1 (shared module fixture). Splitting the file across two commits would have left an intermediate failing state. Committed as one green, hooks-passing commit.

## Threat Mitigations Applied

- **T-15-04 (Tampering / traversal):** `_assert_within(claude_root, dest)` on every GSD destination (tree copies + each skill dir); `test_gsd_path_traversal_is_refused` proves a crafted `../../escape` mapping raises `ValueError`. Source symlinks skipped via the reused `_copy_tree` ignore.
- **T-15-05 (EoP / vendored JS):** copied as data; `test_gsd_install_copies_does_not_execute` trips `subprocess.run`/`Popen`/`os.system` during install and still succeeds — no vendored code, npm, or postinstall runs.
- **T-15-06 (DoS / non-idempotent reinstall):** `dirs_exist_ok` copy + idempotent `_register`; `test_gsd_install_is_idempotent` and `test_gsd_manifest_idempotent_on_reinstall` assert no duplication.
- **T-15-07 (Tampering / clobber):** writes scoped to `.claude/skills/gsd-*` and `.claude/get-shit-done`; `test_gsd_does_not_clobber_user_skills` proves a sibling user skill survives.

## Self-Check: PASSED
