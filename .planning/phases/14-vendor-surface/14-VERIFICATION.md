---
phase: 14-vendor-surface
verified: 2026-07-10T00:00:00Z
status: passed
score: 4/4 success criteria verified (5/5 requirements satisfied)
overrides_applied: 0
re_verification:
  # No previous verification existed — initial verification
gaps: []
---

# Phase 14: Vendor & Surface Verification Report

**Phase Goal:** The two MIT skill sets ship inside FlowState and install themselves, so `flowstate launch` surfaces the real upstream tools with zero manual user install — self-contained from this repo.
**Verified:** 2026-07-10
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `flowstate/skills/gstack/` + `superpowers/` contain vendored MIT SKILL.md trees (59+14=73), each LICENSE present, NOTICE carries both MIT attributions; no repo infra vendored; no new runtime dep | ✓ VERIFIED | `find … -name SKILL.md`: gstack=59, superpowers=14, total=73. Both `LICENSE` files present, MIT verbatim (© 2026 Garry Tan / © 2025 Jesse Vincent). NOTICE lists both vendored sets. No `bin/`/`hooks/`/`bun.lock`/`package.json`/`.git`/symlinks/`.py` under skills. pyproject deps unchanged (click, pydantic, rich, sqlite-vec all pre-existing; fastembed under `[semantic]`) |
| 2 | `flowstate install-skills` (pure-Python) copies vendored skills into `.claude/skills/`; init/kickoff auto-invoke (init respects --dry-run); idempotent, path-safe, manifest-tracked | ✓ VERIFIED | `installer.py::install_skills` uses `shutil.copytree(dirs_exist_ok, symlinks=False, ignore=_ignore_symlinks)`, asserts dest inside `.claude/skills`, records dir-level `InstallEntry`. cli.py: `install-skills` cmd (l.330), init auto-invoke with `dry_run=state.preferences.dry_run` (l.105), kickoff `dry_run=False` (l.144), init sets `dry_run` from flag (l.92). Spot-check: install + idempotent re-run + dry-run-no-copy all PASS |
| 3 | `launch strategy` → `/office-hours`, `launch discipline` → superpowers TDD, gated on installed skills (install-prompt when absent); `discipline` in launch Choice | ✓ VERIFIED | `launcher.py::_SKILL_HANDOFFS` + `_skill_installed` gate on `.claude/skills/<ns>`; install prompt when absent. cli.py l.276 Choice includes `discipline`. Spot-check: installed→`office-hours`/`test-driven-development` present; absent→`install-skills` prompt and handoff token absent. PASS |
| 4 | README reconciled: test count == real collected (1000, not 803/947), URL `obra/superpowers`, doctor 6 checks, sqlite-vec core (only fastembed [semantic]), 3 adapter acks describe real Phase-13 mechanisms | ✓ VERIFIED | `pytest --collect-only` = 1000; README l.254 "1000 tests". No 803/947 in README. l.377 `obra/superpowers` (no 404 URL). l.219 doctor "6 checks" matches `doctor.py::run_doctor` 6-item list. l.381 sqlite-vec "core dependency", fastembed "only piece behind [semantic]". Adapter acks (l.374/375/377): measure→keep/discard, ship/pivot/kill scored rubric, git state+ahead-behind+hook contents that can fail. No "draws on the idea"/"implements a similar" |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/skills/gstack/**` | 59 SKILL.md trees + LICENSE | ✓ VERIFIED | 59 SKILL.md, LICENSE MIT verbatim, office-hours/SKILL.md present |
| `flowstate/skills/superpowers/**` | 14 SKILL.md trees + LICENSE | ✓ VERIFIED | 14 SKILL.md, LICENSE MIT verbatim, test-driven-development/SKILL.md present |
| `NOTICE` | Both MIT attributions | ✓ VERIFIED | Garry Tan + Jesse Vincent, MIT, both upstream URLs |
| `pyproject.toml` | skills shipped, coverage-omitted, no new dep | ✓ VERIFIED | `artifacts=["flowstate/skills/**/*"]`, omit `flowstate/skills/*`, deps unchanged |
| `flowstate/installer.py` | pure-Python path-safe idempotent installer | ✓ VERIFIED | exports `install_skills`; extensible `_NAMESPACES`; path-traversal guard |
| `flowstate/cli.py` | install-skills cmd + init/kickoff wiring + discipline Choice | ✓ VERIFIED | l.330 cmd, l.105/144 auto-invoke, l.276 Choice |
| `flowstate/launcher.py` | gated strategy/discipline handoffs | ✓ VERIFIED | `_SKILL_HANDOFFS`, `_skill_installed`, install prompt |
| `README.md` | reconciled factual claims | ✓ VERIFIED | count 1000, URL, doctor 6, sqlite-vec core, adapter acks |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| installer.py | flowstate/skills/* | `Path(flowstate.__file__).parent/'skills'` | ✓ WIRED (`_skills_source`) |
| cli init/kickoff | installer.install_skills | auto-invoke respecting dry_run | ✓ WIRED (l.105/144) |
| launcher.launch_command | `.claude/skills/{gstack,superpowers}` | presence gate before handoff | ✓ WIRED (`_skill_installed`) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| install-skills creates both namespaces | CliRunner install-skills | office-hours + tdd SKILL.md present | ✓ PASS |
| idempotent re-run | second install-skills | exit 0, no error | ✓ PASS |
| launch strategy/discipline (installed) | CliRunner launch | office-hours / test-driven-development in output | ✓ PASS |
| dry-run no copy | install-skills --dry-run in fresh dir | no `.claude/` created | ✓ PASS |
| launch gating (absent) | launch strategy in uninstalled dir | install-skills prompt, no handoff token | ✓ PASS |
| collected test count | pytest --collect-only | 1000 (matches README) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| VEND-01 | 14-01 | ✓ SATISFIED | 59 gstack SKILL.md + LICENSE + NOTICE © Garry Tan |
| VEND-02 | 14-01 | ✓ SATISFIED | 14 superpowers SKILL.md + LICENSE + NOTICE © Jesse Vincent |
| VEND-03 | 14-03 | ✓ SATISFIED | installer.py + init/kickoff auto-invoke; spot-checked |
| VEND-04 | 14-04 | ✓ SATISFIED | launcher gated handoffs + discipline Choice; spot-checked |
| VEND-05 | 14-02, 14-04 | ✓ SATISFIED | README count 1000, URL, doctor 6, sqlite-vec core, adapter acks; REQUIREMENTS agrees (no 803→947) |

No orphaned requirements — all five VEND IDs declared in plan frontmatter and traced.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none | — | No TBD/FIXME/XXX debt markers in installer.py, launcher.py, cli.py |

Note: 11 `.sh`, `.ts`, `.js` files exist under `flowstate/skills/` — these are legitimate skill-referenced assets living inside SKILL.md directories (e.g. `systematic-debugging/find-polluter.sh`, `gstack-upgrade/migrations/*.sh`), not repo infrastructure. The enumerated forbidden infra (bin/, hooks/, bun.lock, package.json, .git) is confirmed absent. Skills are copied as data, never imported or executed. Not a gap.

### Human Verification Required

None. The install → launch flow was exercised programmatically via CliRunner (install-skills, idempotence, dry-run, launch strategy/discipline installed + absent). Full suite passes 1000 @ 91.77%.

### Gaps Summary

No gaps. All four ROADMAP success criteria are observably true in the codebase, all five VEND requirements are satisfied, key links are wired, behavioral spot-checks pass, and pinned upstream SHAs are recorded in 14-01-SUMMARY (gstack `7c9df1c…`, superpowers `d884ae0…`). Phase goal achieved: the two MIT skill sets ship in-repo and self-install, and `flowstate launch` surfaces them with zero manual user install.

---

_Verified: 2026-07-10_
_Verifier: Claude (gsd-verifier)_
