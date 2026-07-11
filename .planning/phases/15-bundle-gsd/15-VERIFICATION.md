---
phase: 15-bundle-gsd
verified: 2026-07-11T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 15: Bundle GSD Verification Report

**Phase Goal:** GSD ships inside FlowState and installs itself — the user never installs GSD separately, and FlowState never detects or prompts for it. Bundle GSD (MIT © Lex Christopherson) with attribution.
**Verified:** 2026-07-11
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `flowstate/vendor/gsd/` holds pinned GSD (skills + runtime + gsd-sdk w/ node_modules) + verbatim LICENSE + VERSION/commit; NOTICE attribution; platform binary absent; ~51M | ✓ VERIFIED | `du -sh` = 51M; `find -size +10M` empty; no `claude-agent-sdk-*` platform dir; `gsd-sdk.js` invokable → "Bundle GSD"; VERSION pins `1.42.3` + package-lock; LICENSE = MIT © Lex Christopherson verbatim; NOTICE lines 23-28 |
| 2 | `flowstate install-skills` installs GSD UNCONDITIONALLY into `.claude/skills/` + `.claude/get-shit-done/` and makes gsd-sdk invokable — no detect gate, no prompt | ✓ VERIFIED | `installer.install_gsd()` unconditional (no `if present`), called from `install_skills` L263; independent E2E into fresh dir: gsd-sdk.js installed, `get-shit-done/workflows` dir, 67 gsd-* skills; installed `gsd-sdk query roadmap.get-phase 15` → "Bundle GSD", exit 0 |
| 3 | Fresh project: `flowstate launch gsd <N>` works; launcher detect-and-suggest neutralized | ✓ VERIFIED | `launcher.detect_tools` hardwires `{"gsd": True}` (L33); no "not detected"/"new-project" branch in `print_next_steps`; `launch_command('gsd',1)` → `/gsd:plan-phase 1`, `('gsd',None)` → `/gsd:progress` |
| 4 | Documented refresh path (gsd_vendor.py + `flowstate gsd-version`) updates pin deliberately; VERSION inspectable; floating tags refused | ✓ VERIFIED | `gsd_vendor.py`: `read_vendored_version`, `refresh` (pinned-semver-only, rejects `latest`/ranges L278, re-excludes platform binary, fails on >10M, verifies parity), `gsd_provenance` (mirrors pack staleness); `flowstate gsd-version` prints `get-shit-done-cc@1.42.3` + lockfile, exit 0; refresh gated behind `--refresh <version>` |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js` | invokable CLI | ✓ VERIFIED | Present; returns "Bundle GSD" from vendored + installed tree |
| `flowstate/vendor/gsd/LICENSE` | MIT verbatim | ✓ VERIFIED | "MIT License / Copyright (c) 2025 Lex Christopherson" |
| `flowstate/vendor/gsd/VERSION` | 1.42.3 + lockfile | ✓ VERIFIED | Records npm 1.42.3, integrity, lockfile ref, platform-binary-excluded note |
| `flowstate/vendor/VENDORING.md` | canonical procedure | ✓ VERIFIED | Present (3645 bytes) |
| `NOTICE` | GSD + dep attribution | ✓ VERIFIED | "Lex Christopherson", `gsd-build/get-shit-done`, node_modules pointer |
| `flowstate/installer.py` | unconditional install | ✓ VERIFIED | `install_gsd` + `_GSD_TREE_MAPPINGS`; no gate |
| `flowstate/launcher.py` | detect neutralized | ✓ VERIFIED | `detect_tools` = `{"gsd": True}`; branch removed |
| `flowstate/gsd_vendor.py` | refresh/version service | ✓ VERIFIED | Full service mirroring pack.py |
| `flowstate/cli.py` | `gsd-version` command | ✓ VERIFIED | L796 `@main.command("gsd-version")` with `--refresh` |
| `README.md` | bundled reality | ✓ VERIFIED | L58/L377 bundled framing, correct URL, 1045 tests |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `installer.py` | `flowstate/vendor/gsd` | copy runtime + node_modules → `.claude/` | ✓ WIRED (E2E confirmed) |
| `cli.py` | `gsd_vendor.py` | `gsd-version` invokes service | ✓ WIRED (exit 0) |
| `launcher.py` | `launch gsd` | unconditional handoff | ✓ WIRED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Vendored gsd-sdk parity | `node .../gsd-sdk.js query roadmap.get-phase 15` | "Bundle GSD" | ✓ PASS |
| Fresh-project install | `install_skills(tmp)` | gsd-sdk.js + 67 skills + runtime | ✓ PASS |
| Installed gsd-sdk parity | `node <installed>/gsd-sdk.js query ... 15` | "Bundle GSD", exit 0 | ✓ PASS |
| Launch handoff | `launch_command('gsd',1)` | `/gsd:plan-phase 1` | ✓ PASS |
| CLI provenance | `flowstate gsd-version` | `get-shit-done-cc@1.42.3` + lockfile, exit 0 | ✓ PASS |
| Platform binary absence | `find flowstate/vendor/gsd -size +10M` | empty; no `claude-agent-sdk-*` dir | ✓ PASS |
| Tree size | `du -sh flowstate/vendor/gsd` | 51M | ✓ PASS |
| Phase test suite | `pytest test_installer_gsd/test_launcher/test_gsd_vendor` | 52 passed | ✓ PASS |
| Vendor not collected | `pytest --collect-only \| grep flowstate/vendor` | empty | ✓ PASS |
| Test-count truth | `pytest --collect-only` | 1045 (matches README) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| GSD-01 | 15-01 | ✓ SATISFIED | Vendored 51M tree, LICENSE/VERSION/NOTICE, platform binary excluded |
| GSD-02 | 15-02 | ✓ SATISFIED | Unconditional `install_gsd`; E2E install works |
| GSD-03 | 15-03 | ✓ SATISFIED | Launcher detect neutralized; `launch gsd` unconditional |
| GSD-04 | 15-04 | ✓ SATISFIED | `gsd_vendor.py` + `gsd-version`; pinned-only refresh |
| GSD-05 | 15-05 | ✓ SATISFIED | README reconciled; URL fixed; 1045 test count |

All five requirement IDs appear in exactly one plan's `requirements` field and are marked Complete in REQUIREMENTS.md. No orphaned requirements.

### Config / Guardrail Verification

| Check | Status | Evidence |
|-------|--------|----------|
| No new Python runtime deps | ✓ | `dependencies` = click, pydantic, rich, sqlite-vec (unchanged) |
| Coverage omits vendor | ✓ | `pyproject.toml` L50 `omit` includes `flowstate/vendor/*` |
| Pytest skips vendor | ✓ | `conftest.py` `collect_ignore_glob = ["flowstate/vendor/*"]`; 0 vendor paths collected |
| Wheel ships vendor | ✓ | `artifacts = [... "flowstate/vendor/**/*"]` |
| Large-file hook excludes vendor, maxkb unchanged | ✓ | `.pre-commit-config.yaml` L24 `exclude: ^flowstate/vendor/`, L23 `--maxkb=500` |
| Whitespace/EOF hooks exclude vendor | ✓ | L13/L15 `exclude: ^flowstate/(skills\|vendor)/` |

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` markers in any phase-modified source file (`installer.py`, `launcher.py`, `gsd_vendor.py`, `cli.py`).

### Info-Level Note

- README L255 states "1045 tests, 92% coverage". The test count 1045 is exact (matches `pytest --collect-only`). The coverage figure (92% vs the ~91% authoritative full-suite number) differs by <1% due to point-in-time rounding. Not a gap — the flagged concern (real test count, not stale 803/947) is satisfied.

### Human Verification Required

None. All four success criteria are observable programmatically and were independently confirmed via end-to-end install + gsd-sdk invocation (not relying on SUMMARY claims).

### Gaps Summary

No gaps. All four ROADMAP success criteria are VERIFIED against the actual codebase and vendored tree. The vendored GSD (51M, platform binary excluded) is invokable directly and after a fresh install; the installer lays it down unconditionally; the launcher's detect-and-suggest path is neutralized; and a pinned-only refresh path with CLI provenance inspection exists. All guardrails (coverage omit, pytest ignore, wheel include, large-file exclusion, no new deps, README reconciliation) hold.

---

_Verified: 2026-07-11_
_Verifier: Claude (gsd-verifier)_
