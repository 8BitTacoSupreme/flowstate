# FlowState

## What This Is

FlowState is a CLI-first context orchestrator that scaffolds agentic-framework projects (GSD and friends) — it runs a deterministic 5-step pipeline (Context Generation → Research → Strategy → GSD → Discipline), wraps `claude --print` for scoped LLM calls with budget/model overrides, and persists a searchable SQLite FTS5 memory across runs.

Lives at `/Users/jhogan/frameworx`, package `flowstate`, Python 3.12+, Flox-managed env, Claude Code CLI as the LLM bridge.

## Core Value

**Each run starts smarter than the last** — the pipeline produces durable artifacts (PROJECT.md, ROADMAP.md, research/, memory.db) and auto-injects prior findings into subsequent runs, so the work compounds instead of repeating.

If everything else fails, that compounding loop is what FlowState exists to deliver.

## Requirements

### Validated

<!-- Shipped and confirmed valuable through prior milestones (v0.1–v0.2). -->

- ✓ 5-step pipeline orchestrator (research → strategy → gsd → discipline → context) — v0.2
- ✓ Pydantic-validated `flowstate.json` state with backward-compatible migration — v0.2
- ✓ Pluggable `ToolAdapter` pattern (research, strategy, gsd, discipline) — v0.2
- ✓ `ClaudeBridge` subprocess wrapper with `--allowed-tools`, `--max-budget-usd`, `--model`, `--effort` overrides — v0.2
- ✓ Synchronous `EventBus` with priority-ordered, error-isolated handlers — v0.2
- ✓ Persistent memory layer: SQLite + FTS5 (porter stemming, BM25 ranking) with auto-injection as `## Prior Knowledge` — v0.2
- ✓ 8-command Click CLI (`init`, `status`, `launch`, `run`, `context`, `memory`, `check`, `fresh`, `config`) — v0.2
- ✓ Interview flow + deterministic context-file generation (no LLM) — v0.2
- ✓ pytest + pytest-cov with 80% floor enforced via `--cov-fail-under=80` — v0.2

### Active

<!-- This milestone: land the in-flight v2 work + add the "operate this thing safely over time" surface. -->

**Land the v2 pivot (Phase 1):**
- [ ] **PIVOT-01**: Unstaged `cli.py`, `discipline.py`, `launcher.py`, `memory.py`, `config.py` edits commit cleanly with tests green and coverage ≥80%
- [ ] **PIVOT-02**: New `flowstate/config.py` (default-root resolution + precedence: `--root` > saved > cwd) is wired into every CLI command that takes a root
- [ ] **PIVOT-03**: Stale/deleted artifacts (`.planning/PROJECT.md` v1, `.planning/config.json` v1, `CONTEXT.md`) replaced or removed cleanly with no dangling references
- [ ] **PIVOT-04**: `README.md` and `.claude/CLAUDE.md` still accurate after the merge

**Operate-safely trio + hook env-gating (Phase 2, borrowed from ECC):**
- [ ] **INST-01**: `flowstate init` writes an `install_manifest` list onto `FlowStateModel` recording every file it provisioned
- [ ] **INST-02**: `flowstate fresh` consults the manifest instead of blindly deleting — drift and orphans surface; only manifest-owned files are removed
- [ ] **DOCT-01**: `flowstate doctor` reports drift, missing files, schema mismatches, unreachable paths — pure Python diagnose-only, no LLM
- [ ] **DOCT-02**: `flowstate repair` applies the safe subset of doctor's findings (regenerate context files from state, recreate memory.db schema, re-link manifest entries)
- [ ] **STAT-01**: `flowstate status --markdown` renders the Pydantic state as a markdown table (tool status, artifacts, last-run timestamps)
- [ ] **STAT-02**: `flowstate status --markdown --write status.md` writes the rendered output to a file for cross-session handoff
- [ ] **HOOK-01**: `FLOWSTATE_HANDLERS=minimal|standard|strict` env var gates handler registration in `flowstate/events/registry.py` at register time
- [ ] **HOOK-02**: `FLOWSTATE_DISABLED_HANDLERS=name1,name2` env var disables specific named handlers without code edits

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Declarative `hooks.json` per-project hook config** — `@handler` decorator is cleaner for now; revisit only if users need project-scoped hook definitions
- **Continuous-learning / auto "instinct" extraction from sessions** — ECC had silent-content-loss bugs here (v1.4.1 regression); leave promotion of session patterns manual until manual is the bottleneck
- **Cross-harness packaging** (Codex / OpenCode / Cursor adapters) — pulls FlowState off its `claude --print` bridge and adds 3+ install paths; defer until users ask
- **Formal eval/grading harness with pass@k metrics** — premature without enough run history to score against
- **Rust control-plane rewrite** — ECC's `ecc2/` is a 1-maintainer cautionary tale; Python is fine for FlowState's load
- **GUI dashboard** (Tkinter or Electron) — CLI + Rich is on-brand; dashboard is a maintenance sink
- **Paid tier / hosted SaaS / GitHub App** — different business model, not this project

## Context

- **Brownfield, mid-pivot:** v2 work is unstaged on `main` — git status shows `cli.py`, `discipline.py`, `launcher.py`, `memory.py`, plus new `flowstate/config.py` and `tests/test_config.py`, plus deleted `.planning/PROJECT.md` / `.planning/config.json` / `CONTEXT.md`. ~370 lines changed across 7 files. Phase 1 closes this loop.
- **Codebase map fresh:** `.planning/codebase/` was just regenerated (2026-05-25) — STACK, ARCHITECTURE, STRUCTURE, CONVENTIONS, TESTING, INTEGRATIONS, CONCERNS. Use these as canonical reference during planning.
- **ECC comparison done:** Researched `affaan-m/ECC` (192K-star agent-harness performance system, 7-harness packaging, 60 agents, 232 skills, Rust rewrite in flight). Stole 4 patterns into this milestone (Active); explicitly rejected the surface-area-explosion patterns (Out of Scope).
- **Single maintainer.** Granularity choices favor "few broad phases" over many small ones to avoid coordination overhead.

## Constraints

- **Tech stack:** Python 3.12+, Click for CLI, Pydantic for state, SQLite + FTS5 for memory, subprocess for the Claude bridge. No new runtime dependencies in this milestone.
- **Coverage:** ≥80% enforced by `pyproject.toml` (`--cov-fail-under=80`). Pre-commit runs ruff (legacy + format), trailing-whitespace, EOF, large-file, merge-conflict, debug-statement checks.
- **Bridge:** Claude Code CLI v2+ must be locatable; FlowState invokes `claude --print` non-interactively. No direct Anthropic API calls.
- **Compatibility:** State migration must work from v0.1.0 → v0.2.0 → v0.3.0 (this milestone bumps minor).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Coarse granularity (2 phases) | Single maintainer, scope is bounded, "one small phase" was the explicit user framing for the operate-safely work | — Pending |
| Land v2 pivot before adding new surface | Compounding the unstaged work with new features makes the diff unreviewable and the bug surface ambiguous | — Pending |
| Skip Codex/OpenCode/Cursor adapters | ECC ships to 7 harnesses with one maintainer and it's visibly straining; FlowState stays Claude-Code-native until users ask | — Pending |
| Hook profile via env var, not config file | Matches ECC's pattern (`ECC_HOOK_PROFILE`) and avoids a new config surface; one env var + one filter pass at handler register time | — Pending |
| Borrow install-manifest pattern from ECC | `flowstate fresh` is currently destructive without a manifest of what it owns — same gap ECC's `doctor`/`repair` exists to solve | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-25 after milestone-2 initialization (v2 pivot + operate-safely)*
