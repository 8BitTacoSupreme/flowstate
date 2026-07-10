---
phase: 15-bundle-gsd
plan: 01
subsystem: vendor
status: complete
tags: [vendor, gsd, packaging, licensing, provenance]
requires: []
provides:
  - flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js (full-parity gsd-sdk CLI)
  - flowstate/vendor/gsd/LICENSE (GSD MIT verbatim)
  - flowstate/vendor/gsd/VERSION (pinned provenance)
  - flowstate/vendor/VENDORING.md (canonical reproducible procedure)
affects:
  - 15-02 (installer lays down the vendored tree)
  - 15-03 (launcher delegates to vendored gsd)
  - 15-04 (refresh path reuses VENDORING.md)
tech-stack:
  added: [get-shit-done-cc@1.42.3 (vendored Node data, MIT)]
  patterns: [vendor-as-data, lockfile-pinned-provenance, hook/coverage/collection-exclusion]
key-files:
  created:
    - flowstate/vendor/gsd/node_modules/** (~51M, 93 production packages)
    - flowstate/vendor/gsd/LICENSE
    - flowstate/vendor/gsd/VERSION
    - flowstate/vendor/gsd/package-lock.json
    - flowstate/vendor/VENDORING.md
    - conftest.py
  modified:
    - NOTICE
    - pyproject.toml
    - .pre-commit-config.yaml
decisions:
  - "Vendored get-shit-done-cc@1.42.3 with --omit=optional --omit=dev; the ~197M platform claude binary is deliberately EXCLUDED (redundant with the user's own claude, platform-locked). gsd-sdk query path never needs it."
  - "pre-commit exclusions (large-file, check-yaml, whitespace, eof) for ^flowstate/vendor/ were applied in the Task 1 commit as a Rule 3 blocking prerequisite — the tree cannot be committed byte-verbatim without them."
metrics:
  duration: ~6 min
  completed: 2026-07-10
---

# Phase 15 Plan 01: Vendor the Pinned MIT GSD Distribution Summary

Vendored a lean, full-parity GSD install (`get-shit-done-cc@1.42.3`, 51M, platform binary excluded) into `flowstate/vendor/gsd/` with reproducible provenance, verbatim MIT LICENSE, NOTICE attribution, and full isolation from the large-file hook, pytest collection, and coverage — `gsd-sdk` is proven invokable directly from the vendored tree.

## What Was Built

**Task 1 — Lean 51M full-parity GSD tree (commit `fe9dbf6`)**
- `npm install get-shit-done-cc@1.42.3 --omit=optional --omit=dev` in a clean scratch dir → 100 packages, 51M; copied `node_modules/` (93 production packages under node_modules) into `flowstate/vendor/gsd/node_modules/`.
- Platform binary ABSENT: `find flowstate/vendor/gsd -type f -size +10M` returns nothing; no `@anthropic-ai/claude-agent-sdk-*/` platform dir present.
- Provenance captured: `LICENSE` (MIT © 2025 Lex Christopherson, verbatim), `VERSION` (npm 1.42.3 + sha512 integrity + lockfile ref), `package-lock.json` (lockfileVersion 3, 119 locked packages), and `flowstate/vendor/VENDORING.md` (the single canonical procedure 15-04 will reuse).

**Task 2 — Attribution + build/test/commit isolation (commit `5548226`)**
- `NOTICE`: GSD MIT stanza (© 2025 Lex Christopherson, `get-shit-done`, npm `get-shit-done-cc@1.42.3`) + a pointer to the ~100 bundled transitive-dep LICENSE files under `flowstate/vendor/gsd/node_modules/`. Removed the now-stale "does not include: GSD" line since GSD is now bundled.
- `pyproject.toml`: coverage `omit += flowstate/vendor/*`; wheel `artifacts += flowstate/vendor/**/*` (force-include the 51M tree; under PyPI's 100M cap).
- `conftest.py` (new, root): `collect_ignore_glob = ["flowstate/vendor/*"]` — no vendored file is ever collected/executed in the test process (threat T-15-03).

## Invokability Gate (authoritative — recorded verbatim)

Run from the repo root against a project with `.planning/ROADMAP.md`:

```
$ node flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js query roadmap.get-phase 15
  "phase_name": "Bundle GSD",

$ node flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js query config-get commit_docs
true
```

Full `gsd-sdk` parity is proven from the vendored tree with the platform binary absent.

## Metrics

| Metric | Value |
|--------|-------|
| npm version | 1.42.3 (pinned; sha512-3sQoRYFl7v7dju3LXq7sE3pnufGHF7R6xfDU1DaH2+YYe4V6+dhoaUo4KoBHvjtLQ8UATUX3hWofHg+tAUUALQ==) |
| Vendored size (`du -sh flowstate/vendor/gsd`) | **51M** |
| Files >10M | 0 (platform binary absent) |
| Production packages | 93 (node_modules), 119 lockfile entries |
| Bundled LICENSE files | 100 (transitive deps) |
| Full suite | 1000 passed, 91.77% coverage (≥80% gate held) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.pre-commit-config.yaml` vendor exclusions applied in the Task 1 commit**
- **Found during:** Task 1 (committing the tree)
- **Issue:** The plan assigns `.pre-commit-config.yaml` to Task 2, but the vendored tree cannot be committed at all without the exclusions: 5 files exceed the `check-added-large-files --maxkb=500` threshold, and `trailing-whitespace`/`end-of-file-fixer` would rewrite vendored JS/mjs (breaking byte-verbatim provenance).
- **Fix:** Added `exclude: ^flowstate/vendor/` to `check-added-large-files` (global `--maxkb=500` UNCHANGED), `trailing-whitespace`, and `end-of-file-fixer` (widened their existing `^flowstate/skills/` to `^flowstate/(skills|vendor)/`) in the Task 1 commit.
- **Files modified:** `.pre-commit-config.yaml`
- **Commit:** `fe9dbf6`

**2. [Rule 3 - Blocking] `check-yaml` hook excluded for `^flowstate/vendor/`**
- **Found during:** Task 1
- **Issue:** The vendored tree carries 29 `.yml`/`.yaml` files (dep `.github/FUNDING.yml`, eslint configs). `check-yaml` had no exclude and would run against third-party YAML, risking commit blockage and violating byte-verbatim intent. Not in the plan's explicit exclusion list.
- **Fix:** Added `exclude: ^flowstate/vendor/` to the `check-yaml` hook.
- **Files modified:** `.pre-commit-config.yaml`
- **Commit:** `fe9dbf6`

## Threat Mitigations Applied

- **T-15-01 / T-15-SC (Tampering / supply chain):** version pinned to 1.42.3 + `package-lock.json` (sha512 integrity) captured → reproducible, auditable snapshot.
- **T-15-02 (Repudiation / licensing):** GSD LICENSE verbatim + NOTICE MIT attribution + pointer to the 100 bundled dep LICENSE files.
- **T-15-03 (EoP / vendored JS execution):** copied as data only; `conftest.py` keeps the tree out of pytest collection; the only vendored file executed is the read-only `gsd-sdk query` parity check.
- **T-15-13 (DoS / 197M binary bloat):** `--omit=optional` excludes the platform binary; enforced by `find -size +10M` returning nothing + large-file-hook exclusion scoped to `^flowstate/vendor/` (global threshold unchanged).

## Self-Check: PASSED
