---
phase: 02-operate-safely
plan: 03
subsystem: status-reporting
tags: [click, markdown, renderer, handoff, sqlite, fts5, pure-function]

# Dependency graph
requires:
  - phase: 02-operate-safely
    plan: 01
    provides: install_manifest field on FlowStateModel (read-only consumer here)
provides:
  - render_status_markdown(state, root) pure-function renderer in flowstate/status_markdown.py
  - MemoryStore.last_entry_at() public helper (encapsulates SQLite access; no more _conn poking from outside)
  - --markdown flag on flowstate status (emits markdown to stdout via click.echo for clean piping)
  - --write [PATH] flag on flowstate status (writes to file, defaults to status.md in cwd, prints "Wrote: <abspath>")
  - --write implies --markdown semantically
  - Backward-compat preserved: flowstate status (no flags) renders the existing Rich table + banner unchanged
affects: [02-04-hooks (no shared surface; sequential only)]

tech-stack:
  added: []  # No new runtime deps — uses stdlib (re, sqlite3, datetime)
  patterns:
    - "Pure-function renderer: takes state + root, returns str, never raises on missing files"
    - "Em-dash placeholder convention for missing optional fields (—)"
    - "Public memory accessor over private _conn access (encapsulation boundary respected)"
    - "click.echo for raw markdown + path output (Rich would soft-wrap long absolute paths)"
    - "--write flag idiom: is_flag=False + flag_value=default lets `--write` and `--write PATH` both work"

key-files:
  created:
    - flowstate/status_markdown.py
    - tests/test_status_markdown.py
  modified:
    - flowstate/memory.py
    - flowstate/cli.py
    - tests/test_memory.py

key-decisions:
  - "click.echo over console.print for both rendered markdown and 'Wrote:' confirmation — Rich soft-wraps long absolute paths and breaks pipe-friendliness"
  - "render_status_markdown is pure — caller (CLI) handles IO; renderer never raises on missing memory.db or ROADMAP.md"
  - "MemoryStore.last_entry_at() returns datetime|None (not str) so callers don't double-parse the ISO timestamp"
  - "Em-dash (—) over empty cells for missing data — markdown tables render better and the intent reads clearly"
  - "--write implies --markdown — only output format that makes sense to write; reduces flag friction"
  - "Tools table column order locked from CONTEXT.md STAT-01 sketch: Tool | Status | Started | Completed | Duration | Artifacts | Error"

patterns-established:
  - "Public-accessor-first pattern for MemoryStore: any future status/audit code consults documented methods, never _conn"
  - "Pure-function renderer pattern: any future formatted-output command (e.g., doctor report) follows this shape — state + root in, str out, no IO"

requirements-completed: [STAT-01, STAT-02]

# Metrics
duration: ~4min
completed: 2026-05-25
---

# Phase 2 Plan 3: Status Markdown Renderer Summary

**`flowstate status --markdown` emits a 3-section markdown document (tools table, active phase, memory stats) for cross-session handoff; `--write` writes it to a file. Default Rich-table behavior preserved.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-25T19:17:04Z
- **Completed:** 2026-05-25T19:20:57Z
- **Tasks:** 2 / 2
- **Files modified:** 5 (3 source, 2 tests)
- **Test count:** 247 passing (up from 223 before this plan, +24 new tests)
- **Coverage:** 90.61% (well above 80% floor)

## Accomplishments

- **STAT-01 — Markdown renderer landed:** New `flowstate/status_markdown.py` exports `render_status_markdown(state, root) -> str`. Builds a header (project name, generated timestamp, version, root path), tools table (7 columns: Tool/Status/Started/Completed/Duration/Artifacts/Error), active-phase section (reads `.planning/ROADMAP.md` and extracts the first unchecked `Phase N: name` or falls back to the first `### Phase N:` heading), and memory section (per-kind counts + total entries + DB size + last-entry timestamp).
- **STAT-02 — --write flag landed:** `flowstate status --markdown --write status.md` writes the file and prints `Wrote: <absolute path>` via `click.echo` (intentional — `console.print` line-wraps long paths). `--write` accepts an optional PATH (`is_flag=False, flag_value="status.md"`) so both `--write` and `--write /tmp/x.md` work. `--write` implies `--markdown`.
- **MemoryStore.last_entry_at() helper:** New public method returns the `created_at` datetime of the most recently inserted memory, or None for an empty store. Replaces ad-hoc `store._conn.execute(...)` reaches from outside the class.
- **Backward compatibility preserved:** `flowstate status` (no flags) still renders the Rich table + banner exactly as before. Zero regressions in the existing 28 `test_cli.py` tests.

## Task Commits

Strict TDD: failing test → implementation → no refactor needed.

1. **Task 1: MemoryStore.last_entry_at + status_markdown renderer**
   - `931b766` (test): 2 memory tests + 16 renderer/helper tests, all failing
   - `30ccd48` (feat): `last_entry_at()` on MemoryStore, new `flowstate/status_markdown.py` with 4 helper functions + main renderer

2. **Task 2: --markdown and --write CLI flags**
   - `1bd7e16` (test): 6 CLI tests covering backward-compat, stdout output, default write path, explicit write path, --write-implies-markdown, --help
   - `25a9c02` (feat): extended `status` command with `--markdown` (is_flag) and `--write` (`is_flag=False, flag_value="status.md"`); routes through renderer; preserves Rich-table fallback

## Files Created/Modified

**Source (3):**
- `flowstate/status_markdown.py` (NEW, 144 lines) — Pure-function renderer. `_fmt_dt`, `_fmt_duration`, `_fmt_artifacts`, `_fmt_error` helpers + `_render_tools_table`, `_render_active_phase`, `_render_memory_section` section builders + public `render_status_markdown(state, root)`. Never raises on missing files.
- `flowstate/memory.py` — Added `MemoryStore.last_entry_at() -> datetime | None` (17 lines including docstring) between `count` and `clear`. Tolerates bad timestamps via `(TypeError, ValueError)` catch.
- `flowstate/cli.py` — Replaced 16-line `status` command with 49-line version supporting `--markdown` and `--write` options. Default Rich-table path is byte-for-byte identical to the previous implementation.

**Tests (2):**
- `tests/test_status_markdown.py` (NEW, 22 tests) — `TestRenderStatusMarkdown` (10 tests: header, generated/version, tools table header, per-tool rows, em-dash placeholder, no-roadmap, unchecked-phase parsing, no-db, populated-db, never-raises); `TestFormatHelpers` (6 tests: duration completed/running/unstarted, artifact truncation/empty, pipe escape); `TestStatusMarkdownCli` (6 tests: backward-compat, markdown stdout, default --write path, explicit --write, --write implies --markdown, --help lists flags).
- `tests/test_memory.py` — Added `TestLastEntryAt` class (2 tests: empty-store-returns-None, returns-most-recent-timestamp).

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `click.echo` over `console.print` for markdown + "Wrote:" line | Rich soft-wraps long absolute paths with embedded `\n`, which breaks substring assertions and pipe-friendliness (`flowstate status --markdown \| pbcopy`) |
| Pure-function renderer (no IO inside) | Easy to test, no fixtures needed for happy path, caller owns where output goes (stdout vs. file) |
| `last_entry_at()` returns `datetime` not `str` | Caller decides format; consistent with `MemoryEntry.created_at` which is also a `datetime` |
| Em-dash `—` for missing values | Reads better in rendered markdown than empty cells; matches the locked CONTEXT.md sketch |
| `--write` is_flag=False with flag_value | Click idiom for "optional flag with default value" — `--write` alone uses `status.md`, `--write PATH` uses PATH |
| `--write` implies `--markdown` | Writing a Rich table to a file produces ANSI escape codes; markdown is the only sensible written format |
| Renderer reads `.planning/ROADMAP.md` from disk | State doesn't have a "current phase" field; ROADMAP is the source of truth for which phase is active |
| Renderer NEVER raises on missing files | Status is a diagnostic command — must work on brand-new and broken projects alike |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Rich `console.print` soft-wraps long absolute paths with embedded newlines**
- **Found during:** Task 2 (GREEN phase, first test run)
- **Issue:** `test_status_write_default_path` asserted the absolute path appeared in `result.output`, but Rich's `console.print(f"Wrote: {target.resolve()}")` wrapped the long path across multiple lines: `Wrote: \n/private/var/folders/72/...\n-87/test.../status.md`. Substring assertion failed because the path had literal `\n` characters in the middle.
- **Fix:** Switched to `click.echo(f"Wrote: {target.resolve()}")` so the line stays intact. Also matches the pipe/script-friendly philosophy of the markdown output itself (which also uses `click.echo`).
- **Files modified:** `flowstate/cli.py`
- **Verification:** `pytest tests/test_status_markdown.py::TestStatusMarkdownCli::test_status_write_default_path` passes.
- **Committed in:** `25a9c02` (bundled with Task 2 GREEN)

## Verification

- **Test count:** 247 passing (was 223 pre-plan) — +24 new tests for STAT coverage.
- **Coverage:** 90.61% overall, `flowstate/status_markdown.py` at 89% (uncovered lines are the rare "memory.db corrupt" and "no _conn row.keys" branches, both defensive), `flowstate/memory.py` at 97%, `flowstate/cli.py` at 92% (status command paths covered).
- **Manual smoke:** `uv run flowstate status --markdown --root /tmp` produces the 3-section markdown document with em-dash placeholders for the unprovisioned root.
- **Manual smoke:** `uv run flowstate status --help` lists both `--markdown` and `--write` with descriptive help text.
- **Manual smoke:** `uv run flowstate status` (no flags, in the actual project root) still renders the banner + Rich table.
- **Acceptance criteria:** All 6 success criteria in PLAN.md pass:
  1. `flowstate status --markdown > /tmp/status.md` produces markdown with all 4 headings
  2. Tools table has the locked column order
  3. Memory section shows per-kind counts + total + DB size + last entry
  4. `--write` writes the file and prints `Wrote: <absolute path>`
  5. `flowstate status` (no flags) renders the Rich table unchanged
  6. Coverage stays ≥80% (actual: 90.61%)

## Self-Check: PASSED

- File `flowstate/status_markdown.py` exists; contains `def render_status_markdown` (line 123) and references `state.tools` + `MemoryStore`.
- File `flowstate/memory.py` exists; `def last_entry_at` defined (line 286); no other callers reach into `_conn` from outside.
- File `flowstate/cli.py` exists; contains both `"--markdown"` and `"--write"` option strings; `render_status_markdown` imported at use site; backward-compat Rich-table path intact.
- File `tests/test_status_markdown.py` exists; 22 tests across 3 test classes.
- File `tests/test_memory.py` extended with `TestLastEntryAt` (2 tests).
- All 4 task commits exist in git log: `931b766`, `30ccd48`, `1bd7e16`, `25a9c02`.
- Full test suite: 247 passed, 90.61% coverage.
