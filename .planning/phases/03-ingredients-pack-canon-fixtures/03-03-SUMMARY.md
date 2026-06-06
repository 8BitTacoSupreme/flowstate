---
phase: 03-ingredients-pack-canon-fixtures
plan: "03"
subsystem: fixtures
tags: [eval-fixtures, mcp-json, repomix, dx-02, context-generation]
dependency_graph:
  requires: ["03-01"]
  provides: [generate_starter_fixture, scaffold_mcp_json, .planning/fixtures/starter.json, .mcp.json, repomix-pack DX-02 guidance]
  affects: [flowstate/context.py, .claude/CLAUDE.md, tests/test_context.py]
tech_stack:
  added: []
  patterns: [derive-from-interview-answers, _register manifest helper reuse, TDD RED/GREEN]
key_files:
  created: []
  modified:
    - flowstate/context.py
    - .claude/CLAUDE.md
    - tests/test_context.py
decisions:
  - "generate_starter_fixture is a pure function (no I/O) matching the existing generate_* style"
  - "scaffold_mcp_json accepts root: Path for API consistency but is pure — no side effects"
  - "write_context_files count grows from 5 to 7 (fixture + .mcp.json added after brief.md, before context_files assignment)"
  - ".mcp.json included in state.context_files via the shared created-list assignment (MEDIUM-5)"
  - "DX-02 guidance appended to generate_claude_md dedent template as a ## Repomix Pack section"
metrics:
  duration: "7m"
  completed_date: "2026-06-06"
  tasks_completed: 2
  files_changed: 3
---

# Phase 03 Plan 03: ECC-Modeled Eval Fixtures + MCP Registration Summary

**One-liner:** ECC-shaped starter fixture generated from interview answers + repomix .mcp.json scaffold + DX-02 repomix-pack guidance in both generate_claude_md() and FlowState's own .claude/CLAUDE.md.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| RED  | Failing tests for generate_starter_fixture, scaffold_mcp_json, write_context_files integration, DX-02 guidance | 76f2cc2 |
| 1    | Add generate_starter_fixture() and scaffold_mcp_json() to context.py | d90b958 |
| 2    | Wire fixture+.mcp.json into write_context_files; add DX-02 repomix guidance | 333c272 |

## What Was Built

**flowstate/context.py** — two new functions + wiring + DX-02 guidance:

- `generate_starter_fixture(answers, project_name)` (FIX-01/02): Returns ECC-shaped dict with all five required keys (`retrieval_questions`, `acceptance_gates`, `forbidden_actions`, `system_contract`, `few_shot_exemplars`). Derives `system_contract` from `answers.core_problem`, seeds `acceptance_gates` from `answers.milestones` + `test_coverage`, seeds `retrieval_questions` from `answers.ten_x_vision` + `architecture_pattern`. All lists guarantee ≥1 element even for empty `InterviewAnswers`. Pure function, no I/O.

- `scaffold_mcp_json(root)` (PACK-03): Returns exactly `{"mcpServers": {"repomix": {"command": "npx", "args": ["repomix", "--mcp"]}}}` per MEDIUM-3 requirement. Pure function.

- `write_context_files` extended: creates `.planning/fixtures/` dir, writes `starter.json` via `generate_starter_fixture`, registers it on `install_manifest` with `kind="fixture"`; writes `.mcp.json` via `scaffold_mcp_json`, registers with `kind="config"`. Both appear in `state.context_files`. Total files created grows from 5 to 7.

- `generate_claude_md()` gains a `## Repomix Pack` section (DX-02) instructing downstream agents to consult `.planning/codebase/repomix-pack.xml` instead of crawling source files each wave.

**.claude/CLAUDE.md** — FlowState's own project doc gains the same `## Repomix Pack` guidance section (surgical addition, no restructuring).

## Test Coverage

- 23 new tests in `tests/test_context.py`:
  - `TestGenerateStarterFixture` (8 tests): all required keys, empty-answers defaults, exemplar shape, answer derivation for each field, project_name parameter, coverage gate
  - `TestScaffoldMcpJson` (5 tests): mcpServers key, repomix entry, command==npx, args exact shape, full structural assertion
  - `TestWriteContextFilesFixtureAndMcp` (8 tests): fixture file exists, fixture valid JSON, .mcp.json exists+content, .mcp.json in context_files, fixture kind=fixture with checksum, .mcp.json kind=config with checksum, 7-file count
  - `TestGenerateClaudeMdRepomixGuidance` (2 tests): repomix-pack string present, repomix-pack.xml path present

Full suite result: **345 passed, 91.74% coverage** (≥80% gate passed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestWriteContextFiles count assertions expected 5 (pre-Task-2 baseline)**
- **Found during:** Task 2 GREEN phase
- **Issue:** `test_creates_all_files` asserted `len(created) == 5`; `test_updates_state_context_files` asserted `len(state.context_files) == 5` — both correct before fixture+.mcp.json wiring, wrong after
- **Fix:** Updated both assertions to 7 and added existence checks for the two new files
- **Files modified:** tests/test_context.py
- **Commit:** 333c272

**2. [Rule 1 - Bug] TestWriteContextFilesManifest idempotency and count assertions expected 5**
- **Found during:** Task 2 RED test writing
- **Issue:** `test_write_context_files_populates_manifest` asserted len == 5 and did not include fixture/mcp paths; `test_write_context_files_is_idempotent_for_manifest` asserted len == 5
- **Fix:** Updated to 7, added fixture/mcp path assertions and kind checks in TestWriteContextFilesManifest
- **Files modified:** tests/test_context.py
- **Commit:** 76f2cc2 (RED)

**3. [Style] RUF012 — mutable class attribute in TestGenerateStarterFixture**
- **Found during:** RED commit (pre-commit hook)
- **Issue:** `FIXTURE_REQUIRED_KEYS = {...}` is a bare set on a class body — ruff RUF012 requires `ClassVar` annotation
- **Fix:** Added `from __future__ import annotations`, `from typing import ClassVar`, annotated as `ClassVar[set[str]]`
- **Files modified:** tests/test_context.py
- **Commit:** 76f2cc2 (RED)

## Known Stubs

None — `generate_starter_fixture` produces real derived content from interview answers. The fixture is a scaffold (not hand-crafted per project), but this is by design: it is the "starter" fixture Phase 4 will optionally enrich. No UI rendering path exists for fixture content this phase.

## Threat Flags

None — all new surface is under `.planning/` (operator's own project directory). The `.mcp.json` registers only the read-only repomix server as designed (T-03-07 accepted mitigation). Interview answer text is serialized via `json.dumps`, preventing structure injection (T-03-06 accepted).

## Self-Check: PASSED

Files created/exist:
- [x] /Users/jhogan/frameworx/flowstate/context.py (contains `def generate_starter_fixture(` and `def scaffold_mcp_json(`)
- [x] /Users/jhogan/frameworx/.claude/CLAUDE.md (contains `repomix-pack`)
- [x] /Users/jhogan/frameworx/tests/test_context.py (42 tests pass)

Commits exist:
- [x] 76f2cc2 — RED tests
- [x] d90b958 — Task 1 GREEN
- [x] 333c272 — Task 2 GREEN
