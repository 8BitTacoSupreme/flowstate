---
phase: 07-gotchas-accumulator
plan: "01"
status: complete
subsystem: memory/gotchas
tags: [gotchas, memory, dedup, fts5, harvest, pure-python]
completed_date: "2026-06-08"
duration_minutes: 25
tasks_completed: 3
files_changed: 4

dependency_graph:
  requires: []
  provides:
    - MemoryStore.update(entry)  # UPDATE-by-id + FTS re-sync via memories_au trigger
    - capture_gotcha             # dedup/upsert into INSIGHT entries, mirrors GOTCHAS.md
    - harvest_planning_gotchas   # parses VERIFICATION.md + REVIEW.md for prior-phase failures
    - _normalize / _signature    # sha256-based dedup key with volatile-token stripping
    - _parse_frontmatter         # minimal --- line scanner, no PyYAML
    - _rewrite_gotchas_md        # derived mirror rewrite from memory.db
  affects:
    - flowstate/memory.py        # new update() method
    - .planning/GOTCHAS.md       # rewritten on every capture (derived mirror)

tech_stack:
  added: []
  patterns:
    - UPDATE-by-id + AFTER UPDATE FTS trigger (memories_au in memory.py)
    - sha256[:16] signature with normalized message for dedup
    - never-raises try/except on all public entry points (Phase-6 WR-01)
    - bounded file reads capped at 100 KB (anti-DoS for harvester)
    - re-substitution order is load-bearing (paths→ISO ts→hex id→digits)

key_files:
  created:
    - flowstate/gotchas.py       # 390 lines — gotchas accumulator module
    - tests/test_gotchas.py      # 37 tests covering normalization/dedup/harvest/never-raises
  modified:
    - flowstate/memory.py        # MemoryStore.update() added after add()
    - tests/test_memory.py       # TestMemoryStoreUpdate class (3 tests)

decisions:
  - Substitution order in _normalize is load-bearing: paths first (before digit runs clobber
    path separators), ISO timestamps second (before digit runs swallow YYYY-MM-DD digits),
    12-hex run_ids third, then remaining digits. Inverting any step produces false negatives.
  - Path replacement done before lowercasing so Path.name() operates on original mixed-case
    filename characters. The timestamp regex uses [Tt] to handle the lowercased separator.
  - harvest_planning_gotchas implemented in Task 2 (as part of the module foundation) and
    tested in Task 3. The dedup guarantee means double-harvest increments count, not duplicates.
  - _rewrite_gotchas_md sorts by (-count, last_seen desc) so frequently-recurring failures
    sort to the top. The sort is client-side since get_by_kind returns newest-first by created_at.
---

# Phase 7 Plan 1: Gotchas Foundation Summary

**One-liner:** MemoryStore.update() by-id + sha256-signature gotchas accumulator with normalized dedup, GOTCHAS.md mirror, and GSD-artifact harvester (VERIFICATION.md / REVIEW.md).

## What Was Built

### Task 1 — MemoryStore.update(entry)

Added `def update(self, entry: MemoryEntry) -> None` to `MemoryStore` in `flowstate/memory.py`,
immediately after `add()`. Issues a single `UPDATE memories SET ... WHERE id=?` binding the
same 8 columns as `add()` in the same order. The existing `memories_au` AFTER UPDATE trigger
(L61-66) re-syncs the FTS5 virtual table automatically — no manual FTS writes needed. A
missing id (zero rows matched) is a silent no-op that does not raise.

Three tests added to `TestMemoryStoreUpdate`:
- Mutated metadata/summary round-trips via `get()`
- FTS re-syncs: new token found, old-only token absent after update
- Missing id is a no-op

### Task 2 — flowstate/gotchas.py core

Created `flowstate/gotchas.py` (390 lines) with:

- `_normalize(message)` — strips paths→basename, ISO timestamps→`<ts>`, 12-hex run_ids→`<id>`,
  digit runs→`<n>`, collapses whitespace. Path substitution runs before lowercasing (so
  `Path.name` works on mixed-case). ISO regex uses `[Tt]` to handle lowercased separator.
- `_signature(source, message)` — `sha256(source + "|" + _normalize(message))[:16]`. Source
  included so the same message from different origins produces different signatures.
- `capture_gotcha(memory, *, source, message, root, severity, run_id, timestamp)` — scans
  `get_by_kind(INSIGHT, limit=500)` for matching signature; first-seen→`add()` (count=1,
  first_seen=last_seen=now); re-encounter→`update()` (last_seen=now, count+=1, first_seen
  preserved). Full body wrapped in `try/except Exception: return` (Phase-6 WR-01). Calls
  `_rewrite_gotchas_md` after a successful store operation.
- `_rewrite_gotchas_md(root, memory)` — rewrites `.planning/GOTCHAS.md` from memory.db,
  sorted by (-count, last_seen desc). Wrapped in `try/except Exception: pass`.
- `_parse_frontmatter(text)` — minimal `--- ... ---` line scanner. Returns `{}` when first
  non-empty line is not `---`. No PyYAML.

### Task 3 — harvest_planning_gotchas + tests

`harvest_planning_gotchas(memory, root)` globs `.planning/phases/*/*-VERIFICATION.md` and
`*-REVIEW.md`. Each file is bounded-read (100 KB cap). VERIFICATION files: parse frontmatter
`status:`; if not in `{passed, complete, verified}` or a gaps/must-haves section is present,
capture gotchas with `source="verifier"`. REVIEW files: scan lines for BLOCKER/HIGH/MEDIUM
(ReDoS-safe anchored regex); capture with `source="plan-checker"` (severity `error` for
BLOCKER/HIGH, `warning` for MEDIUM). Entire body wrapped in `try/except Exception: return`.
Each per-finding `capture_gotcha` call is itself a never-raises fence so a single bad line
cannot abort the rest.

13 tests added in `TestParseFrontmatter` and `TestHarvestPlanningGotchas`:
- frontmatter parsing with colon-in-value, leading blank lines, malformed no-close-dashes
- VERIFICATION.md failed status and gaps section yield verifier gotchas
- REVIEW.md BLOCKER/HIGH yields plan-checker gotchas; MEDIUM yields warning severity
- no phases dir is a clean no-op
- malformed binary file skipped without raising
- double-harvest deduplicates (count increments, not duplicates)

## Verification

```
455 passed, 2 warnings — coverage 92.26% (gate: 80%)
ruff check: clean
ruff format: clean
grep -c 'import.*bridge' flowstate/gotchas.py → 0
grep -c 'import yaml|from yaml' flowstate/gotchas.py → 0
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ISO timestamp regex failed on lowercase 'T' separator**

- **Found during:** Task 2 implementation + RED test run
- **Issue:** `_normalize()` lowercases the message before running the ISO timestamp regex, but
  the regex used `[T ]` which doesn't match the lowercased `t`. The ISO timestamp was NOT being
  replaced, causing timestamp-variance tests to fail.
- **Fix:** Path substitution moved before `s = s.lower()` (so `Path.name` works on mixed-case
  filenames); ISO regex updated to `[Tt ]` to handle both cases.
- **Files modified:** `flowstate/gotchas.py`
- **Commit:** 71b14f4 (auto-fixed before commit)

**2. [Rule 2 - Missing] `harvest_planning_gotchas` implemented in Task 2**

- The plan placed `_parse_frontmatter` and `harvest_planning_gotchas` in Task 3 as distinct
  deliverables, but structurally they belong to the module foundation. They were implemented
  as part of Task 2 (gotchas.py creation) and tested in Task 3. The TDD gate confirms GREEN:
  all Task 3 tests pass against the Task 2 implementation. No dedup correctness gap.

## Threat Mitigations Applied

All T-07-0x mitigations from the plan's threat register were implemented:
- **T-07-01 (DoS via regex):** bounded reads (100 KB cap), anchored regexes, no nested quantifiers
- **T-07-02 (Tampering):** writes only to `root/.planning/GOTCHAS.md`; glob rooted at `root/.planning/phases`
- **T-07-03 (DoS via raises):** `try/except Exception` on all three entry points
- **T-07-04 (Malformed frontmatter):** `_parse_frontmatter` returns `{}` on non-`---` start; entire harvester wrapped

## Known Stubs

None — all gotchas functionality is fully wired to memory.db with no placeholder data.

## Self-Check

Files created/modified:
- `flowstate/gotchas.py` — exists (390 lines)
- `flowstate/memory.py` — `def update` present
- `tests/test_gotchas.py` — 37 tests
- `tests/test_memory.py` — `TestMemoryStoreUpdate` present

Commits:
- `5a422e1` feat(07-01): add MemoryStore.update(entry)
- `71b14f4` feat(07-01): create flowstate/gotchas.py
- `1d33184` test(07-01): add harvest_planning_gotchas + _parse_frontmatter tests

## Self-Check: PASSED
