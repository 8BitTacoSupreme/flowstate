# Roadmap: FlowState — Milestone 2 (v2 Pivot + Operate-Safely)

## Overview

This milestone closes out the in-flight v2 pivot (unstaged work on main) then adds the
"operate this thing safely over time" surface borrowed from ECC patterns: install manifest,
doctor/repair, status snapshot, and hook env-gating. Two phases; both are self-contained
deliveries that compound the core loop.

## Phases

- [ ] **Phase 1: Land the v2 Pivot** - Commit the unstaged work cleanly, wire config.py into all CLI commands, purge stale artifacts, and bump to v0.3.0
- [ ] **Phase 2: Operate Safely** - Install manifest, doctor/repair, status snapshot, and hook env-gating so the tool is maintainable over time

## Phase Details

### Phase 1: Land the v2 Pivot
**Goal**: The unstaged v2 work is committed, tests are green, config.py is wired everywhere, stale artifacts are gone, and the project is at v0.3.0
**Depends on**: Nothing (first phase)
**Requirements**: PIVOT-01, PIVOT-02, PIVOT-03, PIVOT-04
**Success Criteria** (what must be TRUE):
  1. `git status` is clean — no unstaged edits in cli.py, discipline.py, launcher.py, memory.py, config.py, or their test files
  2. `pytest` passes with coverage >=80% against the committed codebase
  3. `flowstate --root /some/path <any-command>` resolves the root via the PIVOT-02 precedence chain (explicit > saved > cwd) without error
  4. `grep -r "CONTEXT.md\|\.planning/PROJECT.md\|\.planning/config.json" --include="*.py" --include="*.md"` returns no dangling references to deleted artifacts
  5. `pyproject.toml` version reads `0.3.0` and `README.md` / `.claude/CLAUDE.md` reflect the post-pivot CLI surface
**Plans**: TBD

### Phase 2: Operate Safely
**Goal**: Users can inspect, validate, and maintain a FlowState installation without destructive surprises — manifest-tracked files, a pure-Python health check, a markdown status snapshot, and env-var hook gating are all wired in
**Depends on**: Phase 1
**Requirements**: INST-01, INST-02, INST-03, DOCT-01, DOCT-02, STAT-01, STAT-02, HOOK-01, HOOK-02
**Success Criteria** (what must be TRUE):
  1. After `flowstate init`, `flowstate.json` contains an `install_manifest` listing every file written (path, owner, kind, created_at, checksum); `flowstate fresh` removes only those entries and reports any non-manifest files as orphaned rather than deleting them
  2. `flowstate doctor` exits 0 on a healthy install and exits non-zero when a manifest file is missing, a checksum has drifted, or `claude` is absent from PATH — output is human-readable
  3. `flowstate repair` regenerates missing context files from `state.interview` and resets stale Running statuses; destructive operations (orphan deletion, memory row drops) require `--apply-destructive`
  4. `flowstate status --markdown > /tmp/status.md` produces a valid markdown file containing a tool-status table, active phase section, and memory stats section
  5. `FLOWSTATE_HANDLERS=minimal flowstate run` registers only memory-storage handlers; `FLOWSTATE_DISABLED_HANDLERS=audit_handler flowstate run` skips that handler regardless of profile
**Plans**: TBD
**UI hint**: no

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Land the v2 Pivot | 0/TBD | Not started | - |
| 2. Operate Safely | 0/TBD | Not started | - |
