---
phase: 15-bundle-gsd
plan: 04
status: complete
subsystem: infra
tags: [gsd, vendoring, npm, provenance, cli, staleness]

# Dependency graph
requires:
  - phase: 15-01
    provides: "the vendored flowstate/vendor/gsd/ snapshot (VERSION 1.42.3 + package-lock.json + VENDORING.md canonical procedure)"
provides:
  - "flowstate/gsd_vendor.py — inspectable pinned-version reader + read-only provenance report + deliberate pinned-only refresh encoding the canonical lean-install procedure"
  - "flowstate gsd-version CLI — prints the pinned GSD npm version/lockfile provenance; --refresh <exact-semver> deliberately re-vendors"
affects: [bundle-gsd, installer, doctor, vendoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vendor service mirrors pack.py: binary locator + result dataclass + read-only staleness/provenance function"
    - "Executable form of a Markdown procedure (VENDORING.md) so snapshot and refresh cannot diverge"
key-files:
  created:
    - flowstate/gsd_vendor.py
    - tests/test_gsd_vendor.py
  modified:
    - flowstate/cli.py

key-decisions:
  - "Refresh is pinned-only: an exact semver regex refuses moving tags (latest/next) and ranges (^, ~, >=, 1.x) before touching anything (T-15-11)"
  - "Inspection (read_vendored_version / gsd_provenance) is strictly read-only — no network, no writes — so there is no silent snapshot drift (T-15-10)"
  - "The gsd-sdk parity gate is the ONLY vendored code the refresh executes; it runs against the freshly-installed tree before overwriting the committed one, and any failure leaves the snapshot untouched"
  - "gsd_vendor.py is the single executable source of truth for VENDORING.md's procedure; the CLI help points operators back to VENDORING.md"

patterns-established:
  - "GSD provenance report mirrors flowstate.pack.is_pack_stale: on-disk, mutation-free, surfaces pin + lockfile + lean-install invariants (platform binary excluded, no file >10M)"
  - "Deliberate-mutation CLI: default invocation inspects; an explicit --refresh <version> flag is the only path that rewrites the vendored tree"

requirements-completed: [GSD-04]

# Metrics
duration: ~18min
completed: 2026-07-10
---

# Phase 15 Plan 04: Documented GSD Refresh / Staleness Path Summary

**A pinned-only, inspection-never-mutates GSD refresh service (`flowstate/gsd_vendor.py` + `flowstate gsd-version`) that encodes VENDORING.md's one canonical lean-install procedure, so the vendored GSD snapshot is auditable and can only be updated deliberately.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2 (Task 1 was TDD)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments
- Added `flowstate/gsd_vendor.py`: a version/provenance reader plus a deliberate `refresh(version)` that re-applies 15-01's exact `npm install get-shit-done-cc@<pin> --omit=optional --omit=dev` procedure — re-excluding the optional platform binary, failing on any file >10M, and verifying `gsd-sdk` parity before overwriting the committed tree.
- Surfaced `flowstate gsd-version`: inspects the pinned npm version + lockfile/integrity provenance by default; `--refresh <exact-semver>` gates the deliberate re-vendor and refuses moving tags/ranges (exit 2).
- Mirrored `flowstate pack`'s locator + result-dataclass + read-only staleness shape, and made `gsd_vendor.py` the single executable form of `flowstate/vendor/VENDORING.md` so the snapshot and any refresh cannot diverge.
- No new Python runtime dependency; all tests offline (fake `npm`/`node` shell scripts drive the full procedure — no live install, no network).

## Task Commits

1. **Task 1: GSD refresh + version-inspection service (TDD)** — `9e99a49` (feat; RED+GREEN combined in one commit because the pre-commit pytest+coverage gate must pass on every commit)
2. **Task 2: gsd-version CLI surface + docs** — `196290f` (feat)

## Files Created/Modified
- `flowstate/gsd_vendor.py` — `_find_npm`/`_find_node` locators, `VendoredVersion`/`RefreshResult` dataclasses, `read_vendored_version()`, `gsd_provenance()` (read-only), `_is_pinned_version()` (pinned-semver guard), and `refresh()` (deliberate lean re-install + parity gate).
- `flowstate/cli.py` — `@main.command("gsd-version")` with `--refresh VERSION`; prints provenance, gates refresh behind an exact-semver flag, documents the procedure in help text.
- `tests/test_gsd_vendor.py` — 28 offline tests: locator, pinned-tag matrix, version read, provenance (incl. mutation-free + oversize/platform-binary flags), refresh guards + full fake-npm/node happy path + failure modes, and CliRunner coverage.

## Verification
- `flowstate gsd-version` prints `get-shit-done-cc@1.42.3` + lockfile + integrity + "platform binary excluded: yes" (real tree, smoke-tested).
- Default invocation never calls `refresh` (test asserts a monkeypatched refresh is never hit).
- `--refresh latest` / `^1.42.3` refused with a pinned-semver error; failed/oversize/parity-fail refreshes leave the committed VERSION byte-identical.
- Full suite: **1045 passed, 91.07% coverage** (≥80% gate); ruff check + format clean; pre-commit hooks passed on both task commits (no `--no-verify`).

## Deviations from Plan

None — plan executed as written. (Note: TDD RED and GREEN were committed together in `9e99a49` rather than as separate commits, because the project's pre-commit gate runs `pytest --cov-fail-under=80` and rejects any commit whose working tree has failing tests; a standalone RED commit is impossible under that constraint.)

## Threat Coverage
- **T-15-10 (silent snapshot drift):** inspection paths are read-only; only an explicit `--refresh <pin>` mutates the tree — asserted by `test_default_invocation_never_refreshes` + `test_provenance_does_not_mutate_tree`.
- **T-15-11 (re-install privilege):** refresh refuses moving tags, re-excludes the platform binary, fails on any file >10M, and verifies `gsd-sdk` parity before overwriting — asserted by the refresh-procedure tests.
- **T-15-12 (provenance visibility):** npm version + lockfile + integrity are printed by `flowstate gsd-version`; the procedure is the single documented source of truth shared with `VENDORING.md`.

## Self-Check: PASSED
