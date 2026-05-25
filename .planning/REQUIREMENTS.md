# Requirements: FlowState (Milestone 2 — v2 Pivot + Operate-Safely)

**Defined:** 2026-05-25
**Core Value:** Each run starts smarter than the last — durable artifacts + auto-injected memory make work compound across runs.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Pivot (land the in-flight v2 work)

- [ ] **PIVOT-01**: Unstaged edits to `flowstate/cli.py`, `flowstate/discipline.py`, `flowstate/launcher.py`, `flowstate/memory.py`, `flowstate/config.py` (new), `tests/test_cli.py`, `tests/test_discipline.py`, `tests/test_launcher.py`, `tests/test_config.py` (new) commit cleanly with the full pytest suite green and coverage ≥80%
- [ ] **PIVOT-02**: `flowstate/config.py` default-root resolution (`--root` > saved `~/.config/flowstate/config.toml` > cwd) is wired into every CLI command that accepts a root path; precedence is covered by `tests/test_config.py`
- [ ] **PIVOT-03**: Deleted artifacts (`.planning/PROJECT.md` v1, `.planning/config.json` v1, `CONTEXT.md`) are either replaced by the new GSD-managed equivalents or removed cleanly — no orphaned references in code, README, or docs
- [ ] **PIVOT-04**: `README.md` and `.claude/CLAUDE.md` reflect the post-pivot CLI surface and architecture; `pyproject.toml` version bumped to `0.3.0`

### Install Manifest (INST)

- [x] **INST-01**: `FlowStateModel` (in `flowstate/state.py`) gains an `install_manifest: list[InstallEntry]` field where each entry records `path`, `owner` (which init step wrote it), `kind` (config / context / memory / research), `created_at`, and `checksum`
- [x] **INST-02**: `flowstate init` populates the manifest for every file it writes (PROJECT.md, ROADMAP.md, CLAUDE.md, config.json, research/brief.md, memory.db, plus any tool-adapter artifacts); state migration adds the field with backfill from the existing filesystem when loading a pre-manifest `flowstate.json`
- [x] **INST-03**: `flowstate fresh` consults the manifest instead of blindly deleting — only files recorded as owned by FlowState are removed; non-manifest files in `.planning/` are reported as "orphaned" and left in place unless `--force` is passed

### Doctor / Repair (DOCT)

- [ ] **DOCT-01**: `flowstate doctor` (new Click command, pure Python, no LLM) produces a structured report covering: manifest drift (missing or mutated files vs. checksums), memory.db schema mismatch, broken `--root` resolution, missing Claude CLI on PATH, stale tool status (e.g., Running for >24h), orphaned files in `.planning/`. Exits non-zero when any check fails so it composes in CI/precommit
- [ ] **DOCT-02**: `flowstate repair` applies the safe subset of doctor's findings: regenerate missing context files from `state.interview`, recreate `memory.db` schema and FTS5 triggers if drifted, reset stale Running statuses to Blocked, rewrite manifest checksums after intentional regenerations. Destructive fixes (delete orphans, drop memory rows) gated behind `--apply-destructive`

### Status Snapshot (STAT)

- [x] **STAT-01**: `flowstate status --markdown` renders the current Pydantic state as a markdown handoff — one table for tool status (Ready/Running/Completed/Blocked + last-run timestamp + artifact paths), one section for active phase, one section for memory stats (entry count by kind, total tokens of context available)
- [x] **STAT-02**: `flowstate status --markdown --write [path]` writes the rendered output to the given path (default `status.md` in cwd); stdout shows a one-line confirmation and the absolute path written

### Hook Profile (HOOK)

- [x] **HOOK-01**: `FLOWSTATE_HANDLERS=minimal|standard|strict` env var read in `flowstate/events/registry.py` at handler-register time; each `@handler` decorator gains a `profile=` kwarg with default `standard`; handlers whose profile is stricter than the current setting are skipped at registration. Default = `standard`; setting to `minimal` registers only memory-storage handlers; `strict` registers everything plus extra audit handlers
- [x] **HOOK-02**: `FLOWSTATE_DISABLED_HANDLERS=name1,name2` env var (comma-separated handler names) skips specific handlers regardless of profile; takes precedence over `FLOWSTATE_HANDLERS`. Covered by `tests/test_events_registry.py`

## v2 Requirements

Deferred to future milestones.

### Distribution (DIST)

- **DIST-01**: Publish to PyPI as `flowstate-orchestrator` (name TBD, current `flowstate` is taken)
- **DIST-02**: Flox manifest entry for one-command install via Flox catalog
- **DIST-03**: Homebrew formula (tap or core)

### Cross-Harness (XHARN)

- **XHARN-01**: Codex CLI adapter (write `AGENTS.md` equivalent of CLAUDE.md, route bridge calls)
- **XHARN-02**: OpenCode adapter
- **XHARN-03**: Cursor rules generation

### Evaluation (EVAL)

- **EVAL-01**: Capture pipeline outputs in `runs/` for post-hoc grading
- **EVAL-02**: pass@k evaluator over historical runs

## Out of Scope

Explicitly excluded for this milestone. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Declarative `hooks.json` per-project hook config | `@handler` decorator is cleaner; revisit only if users need project-scoped hook definitions. ECC's 50KB hooks.json is a smell. |
| Continuous-learning / auto "instinct" extraction | ECC v1.4.1 had silent content-loss bug here; leave promotion of session patterns to memory.db manual until manual is the bottleneck |
| Cross-harness packaging (Codex/OpenCode/Cursor) | Multiplies install paths and bridge surfaces; defer to v2 milestone if users request |
| Formal eval/grading harness with pass@k | Premature without enough run history to score against; defer to v2 |
| Rust control-plane rewrite | ECC's `ecc2/` is a cautionary tale for solo maintainers running parallel runtimes; Python is fine for FlowState's load |
| GUI dashboard (Tkinter / Electron) | CLI + Rich is on-brand; dashboard is a maintenance sink |
| Paid tier / hosted SaaS / GitHub App | Different business model entirely |
| Semantic embeddings on top of FTS5 | FTS5 BM25 is working; embeddings add a dependency (and likely a vector DB) for marginal gain at current scale |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIVOT-01 | Phase 1 | Complete |
| PIVOT-02 | Phase 1 | Complete |
| PIVOT-03 | Phase 1 | Complete |
| PIVOT-04 | Phase 1 | Complete |
| INST-01 | Phase 2 | Complete |
| INST-02 | Phase 2 | Complete |
| INST-03 | Phase 2 | Complete |
| DOCT-01 | Phase 2 | Pending |
| DOCT-02 | Phase 2 | Pending |
| STAT-01 | Phase 2 | Complete |
| STAT-02 | Phase 2 | Complete |
| HOOK-01 | Phase 2 | Complete |
| HOOK-02 | Phase 2 | Complete |

**Coverage:**
- v1 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-25*
*Last updated: 2026-05-25 after initial definition*
