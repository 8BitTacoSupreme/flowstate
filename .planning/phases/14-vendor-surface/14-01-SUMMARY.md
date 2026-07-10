---
phase: 14-vendor-surface
plan: 01
subsystem: packaging
status: complete
tags: [vendoring, licensing, packaging, skills]
requires: []
provides:
  - flowstate/skills/gstack/**
  - flowstate/skills/superpowers/**
  - NOTICE attributions for both MIT skill sets
affects:
  - flowstate installer (14-03)
  - flowstate launch surface (14-04)
tech-stack:
  added: []
  patterns:
    - "vendored third-party data lives under flowstate/skills/, git-tracked, shipped in the wheel via hatchling artifacts"
    - "vendored trees excluded from formatting hooks (trailing-whitespace/eof-fixer) to preserve verbatim fidelity"
key-files:
  created:
    - flowstate/skills/gstack/ (59 SKILL.md trees + LICENSE, 126 files)
    - flowstate/skills/superpowers/ (14 SKILL.md trees + LICENSE, 41 files)
  modified:
    - NOTICE
    - pyproject.toml
    - .pre-commit-config.yaml
decisions:
  - "Prune node/build tooling from within skill trees (Rule 1/2 deviation): the literal 'copy full tree' rule pulled 30MB of gstack TypeScript implementations + nested bin/; the plan's own acceptance criterion ('no bin/ anywhere') and threat T-14-02 (data-only) require stripping src/test/bin/daemon/scripts/vendor + build config while keeping all skill documentation and referenced assets."
  - "Exclude flowstate/skills/ from trailing-whitespace + end-of-file-fixer hooks so vendored LICENSE/SKILL.md stay byte-verbatim."
metrics:
  duration: ~12 min
  completed: 2026-07-10
  tasks: 2
  files: 170
---

# Phase 14 Plan 01: Vendor Surface Summary

Vendored the full gstack (59 skills) and superpowers (14 skills) MIT skill sets into `flowstate/skills/` as documentation-only trees, each with its upstream LICENSE verbatim, both attributed in NOTICE, packaged into the wheel and kept out of the coverage denominator.

## Pinned Upstream SHAs

| Upstream | Repo | License | SHA |
|----------|------|---------|-----|
| gstack | https://github.com/garrytan/gstack | MIT © 2026 Garry Tan | `7c9df1c568a9ea745508f679a329332b2c338063` |
| superpowers | https://github.com/obra/superpowers | MIT © 2025 Jesse Vincent | `d884ae04edebef577e82ff7c4e143debd0bbec99` |

Both cloned fresh over HTTPS into the session scratchpad; SHAs captured with `git rev-parse HEAD` before copying. No package-manager install performed (T-14-SC).

## What Shipped

- `flowstate/skills/gstack/` — 59 SKILL.md trees (incl. `sections/`, `docs/`, `templates/`, `references/`, `migrations/`, manifests, and referenced `.md`/`.html`/`.template`/example assets) + `LICENSE` verbatim. 126 files.
- `flowstate/skills/superpowers/` — 14 SKILL.md trees (rooted at the upstream `skills/` dir so `superpowers/test-driven-development/SKILL.md` resolves) + `LICENSE` verbatim. 41 files.
- `NOTICE` — both MIT attributions added under an "includes vendored skill sets" section (© Garry Tan, © Jesse Vincent).
- `pyproject.toml` — `artifacts = ["flowstate/skills/**/*"]` forces the non-Python data into the wheel; `flowstate/skills/*` added to `[tool.coverage.run] omit`.
- Total vendored surface: 167 files, 4.4M (down from 36M before pruning infra).

## Tasks

| Task | Name | Commit | Key files |
|------|------|--------|-----------|
| 1 | Clone at pinned SHAs and vendor the SKILL.md trees | c85441c | flowstate/skills/**, .pre-commit-config.yaml |
| 2 | NOTICE attributions + wheel/coverage config | 3fa7571 | NOTICE, pyproject.toml |

## Deviations from Plan

### Auto-fixed / adjusted

**1. [Rule 1 + Rule 2 — scope correctness] Pruned node/build tooling from within skill trees**
- **Found during:** Task 1. The plan's literal instruction ("copy that directory's full tree") applied to gstack's `browse/`, `make-pdf/`, and `ios-qa/` skills pulled in their full TypeScript implementations, test suites, a node security-sidecar daemon, and nested `bin/` executables — 36M / 521 files.
- **Why a deviation was required, not optional:** the plan's own Task 1 acceptance criterion states "No `bin/`, `hooks/`, `bun.lock`, or `package.json` anywhere under `flowstate/skills/`", and `browse/bin/` violated it. Threat T-14-02 (mitigate) mandates "data only, never executed, no runtime infra". Shipping 30M of third-party browser-automation source into every user's `~/.claude/skills` via the 14-03 installer is exactly the supply-chain surface the threat model exists to prevent.
- **Fix:** vendored by pruning well-known build/runtime dirs (`src`, `test`, `tests`, `bin`, `scripts`, `daemon`, `vendor`, `node_modules`, `dist`, `build`) and build-config files (`*.tmpl`, `package.json`, `tsconfig*.json`, `*.lock`, `bunfig.toml`) from every skill tree, while keeping all skill documentation and legitimately skill-referenced assets (SKILL.md, `sections/`, `docs/`, `templates/`, `references/`, `migrations/*.sh`, manifests, example `.ts`/`.js`/`.dot`, `.html`/`.png`/`.template`). Result: 4.4M / 167 files, all 59+14 SKILL.md preserved.
- **Files:** flowstate/skills/**
- **Commit:** c85441c

**2. [Rule 3 — blocking issue] Excluded vendored data from formatting hooks**
- **Found during:** Task 1. `trailing-whitespace` and `end-of-file-fixer` pre-commit hooks would rewrite 3 vendored files (2 trailing-whitespace, 1 missing final newline) and abort the commit — corrupting the must-have "each tree carries its upstream LICENSE verbatim".
- **Fix:** added `exclude: ^flowstate/skills/` to both hooks in `.pre-commit-config.yaml`. Standard practice for vendored third-party data.
- **Commit:** c85441c

`.pre-commit-config.yaml` was not in the plan's `files_modified` list; it was a required supporting change to land verbatim vendored data through the commit gate.

## Verification

- Task 1 automated verify: PASS (office-hours/SKILL.md, test-driven-development/SKILL.md, both LICENSEs present; no bin/hooks/bun.lock/package.json anywhere).
- Task 2 automated verify: PASS (NOTICE has "Garry Tan" + "Jesse Vincent" + MIT; pyproject references skills; runtime resolves at `Path(flowstate.__file__).parent/'skills'`).
- Full suite: `985 passed`, coverage **92.07%** (≥80 gate; unchanged by vendored data — no `.py` in skills + omit rule).
- Wheel-content verification deferred: hatchling is a build-isolation-only dep (not installed in `.venv`), so an actual `build`/`pip wheel` could not run offline. Packaging correctness rests on (a) files git-tracked under `flowstate/` (hatchling default VCS inclusion) and (b) the explicit `artifacts` force-include.

## Notes / Downstream

- Skills are DATA — FlowState (Python) never imports or executes them; they are copied for Claude Code. The 14-03 installer resolves them at `Path(flowstate.__file__).parent / "skills"` per the plan's `key_links`.
- The gstack repo-root router `SKILL.md` was vendored as a standalone file (its "directory" is the whole repo — not copied wholesale). `SKILL.md.tmpl` (its build source, "do not edit — regenerate with bun") was excluded; the generated `SKILL.md` is the shipped artifact.

## Self-Check: PASSED

- FOUND: flowstate/skills/gstack/office-hours/SKILL.md
- FOUND: flowstate/skills/superpowers/test-driven-development/SKILL.md
- FOUND: flowstate/skills/gstack/LICENSE
- FOUND: flowstate/skills/superpowers/LICENSE
- FOUND: commit c85441c
- FOUND: commit 3fa7571
