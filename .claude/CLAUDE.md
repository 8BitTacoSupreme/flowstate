# FlowState — The Context Orchestrator

**Repo:** `/Users/jhogan/frameworx` · **Package:** `flowstate`

## Problem

Agentic frameworks like GSD need scaffolding before they can do useful work: PROJECT.md, ROADMAP.md, CLAUDE.md, config files, plus enough research and strategy to ground the first phase. Producing all of that by hand is slow, inconsistent, and forgets what previous runs already learned.

## Vision

A CLI-first orchestrator that runs a deterministic 5-step pipeline — **Context Generation → Research → Strategy → GSD → Discipline** — wraps `claude --print` for scoped LLM calls, persists state across runs, and accumulates a searchable memory of findings so each new project starts smarter than the last.

## Architecture

- **Pattern:** Event-driven orchestrator with pluggable tool adapters and persistent state/memory
- **CLI surface:** Click-based, 8 commands (`init`, `status`, `launch`, `run`, `context`, `memory`, `check`, `fresh`, `config`)
- **State:** Pydantic-validated `flowstate.json` — tool status, artifacts, interview answers, preferences
- **Memory:** SQLite + FTS5 (`memory.db`) with BM25 ranking; auto-injected into subsequent runs as `## Prior Knowledge`
- **Bridge:** Non-interactive `claude --print` subprocess with `--allowed-tools`, `--max-budget-usd`, `--model`, `--effort` overrides
- **Sandbox:** `sandbox.py` `wrap(cmd, surface, project_root, env, *, tier)` seam wraps every agent subprocess. Default `observe` tier = non-blocking env-scrub (secret-shaped vars stripped, Claude auth vars carved out); opt-in `confine` tier = macOS Seatbelt/SBPL + Linux bwrap+Landlock (denies writes outside `project_root` + `~/.ssh` reads, auth survives), fails loud with `SandboxUnavailableError` if no confinement is achievable. Set via `ProjectPreferences.sandbox` (default `observe`). Blast-radius reducer, not egress control.
- **Events:** Synchronous `EventBus` (`StepCompleted` / `StepFailed`) drives memory handlers and audit hooks
- **Test coverage:** 80% enforced (`pytest --cov-fail-under=80`)
- **Tooling:** Flox for reproducible env · ruff + pre-commit · pytest + pytest-cov

## Active Tools

- `research` — split-topic `claude --print` calls → `research/report.md`
- `strategy` — single pressure-test call → `research/strategy.md`
- `gsd` — writes `.planning/` context files for the GSD skill set
- `discipline` — pure-Python audit of git, tests, hooks (no LLM)

## Current Phase

See `.planning/ROADMAP.md` for phase details. Codebase reference docs live in `.planning/codebase/` (run `/gsd:map-codebase` to refresh).

## Repomix Pack

When analyzing the FlowState codebase, consult `.planning/codebase/repomix-pack.xml`
instead of crawling source files each wave. The pack is updated by `flowstate pack`.
Use the repomix MCP server (`mcp__repomix`) for targeted retrieval from the pack.

## SUMMARY Frontmatter Convention

Every quick-task and phase SUMMARY file should carry a `status:` field in its YAML
frontmatter. Allowed values: `complete`, `verified`, `blocked`, `paused`, `drafted`.

`gsd-sdk query audit-open` treats only `complete` (and `resolved`) as terminal — shipped
work must be marked `complete` to avoid false-positive in-flight flags at milestone close.

Quick-task directories also need a bare `SUMMARY.md` (in addition to `{id}-SUMMARY.md`)
because the SDK audit scanner only resolves `SUMMARY.md`, not the per-task named form.
