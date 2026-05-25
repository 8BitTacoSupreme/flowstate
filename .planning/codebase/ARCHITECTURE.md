# Architecture

**Analysis Date:** 2026-05-25

## Pattern Overview

**Overall:** Event-driven orchestrator with modular adapter pattern and persistent state/memory.

FlowState is a **5-step agentic pipeline orchestrator** that prepares context files for Claude Code tools (GSD, Research, Strategy, Discipline). It uses a synchronous event bus for cross-step coordination, persists all state to `flowstate.json`, and maintains a searchable SQLite FTS5 memory store for knowledge continuity across runs.

**Key Characteristics:**
- **CLI-first:** 8 Click commands (init, status, launch, run, context, memory, check, fresh, config)
- **Non-interactive bridge:** Wraps `claude --print` with scoped tool permissions and budget/model overrides
- **Pure Python where possible:** Context generation, discipline audit, memory store are not LLM-dependent
- **Adapter pattern:** Each tool (research, strategy, gsd, discipline) is a pluggable ToolAdapter subclass
- **Event-driven coordination:** StepCompleted/StepFailed events trigger memory handlers for auto-storage
- **Stateful:** flowstate.json tracks each tool's status (Ready/Running/Completed/Blocked), artifacts, timestamps

## Layers

**CLI Layer:**
- Purpose: User-facing commands and option parsing
- Location: `flowstate/cli.py`
- Contains: 8 Click command groups (main, memory, config) with option handling for dry-run, model override, budget override
- Depends on: config, state, orchestrator, interview, launcher, memory, bridge, discipline, context
- Used by: End users via `flowstate init|status|launch|run|context|memory|check|fresh|config`

**State Management Layer:**
- Purpose: Persistence and validation of pipeline state
- Location: `flowstate/state.py`
- Contains: Pydantic models (FlowStateModel, ToolState, InterviewAnswers, ProjectPreferences) and load/save/migrate functions
- Depends on: pydantic, pathlib
- Used by: Orchestrator, CLI, all adapters; calls `load_state()` and `save_state()` after each pipeline step

**Orchestrator Layer:**
- Purpose: Sequences the 5-step pipeline and coordinates tool execution
- Location: `flowstate/orchestrator.py`
- Contains: `run_pipeline()` (main entry), `run_phase()` (single GSD phase), `print_status()` (table output), `_run_step()` (generic step runner with status/artifact tracking), `_make_bridge()` (bridge config builder)
- Depends on: state, bridge, context, all tool adapters, memory, events
- Used by: CLI commands `init`, `run`, `status`

**Interview Layer:**
- Purpose: Interactive intake questionnaire for problem/vision/milestones
- Location: `flowstate/interview.py`
- Contains: `run_interview()` (main loop), section definitions (research, strategy, management, discipline) with custom prompt per section
- Depends on: rich, state
- Used by: CLI `init` command when `--skip-interview` is not set

**Context Generation Layer:**
- Purpose: Deterministic, non-LLM file generation from interview answers
- Location: `flowstate/context.py`
- Contains: Template functions `generate_project_md()`, `generate_roadmap_md()`, `generate_gsd_config()`, `generate_claude_md()` that produce JSON/Markdown consumed by downstream tools
- Depends on: state, textwrap (no LLM)
- Used by: Orchestrator during pipeline, CLI `context` command for regeneration

**Tool Adapter Layer:**
- Purpose: Pluggable interface for each stage (research, strategy, gsd, discipline)
- Location: `flowstate/tools/` — base.py, research.py, strategy.py, gsd_adapter.py
- Contains:
  - Base: `ToolAdapter` (abstract parent), `ToolResult` dataclass
  - Research: `ResearchAdapter` (splits topics, one bridge call per topic, merges into research/report.md)
  - Strategy: `StrategyAdapter` (single pressure-test bridge call, writes research/strategy.md)
  - GSD: `GSDAdapter` (writes .planning/ context files, no bridge call)
  - Discipline: In `discipline.py` — `check_setup()` audits git/test/hooks without LLM
- Depends on: bridge, memory (optional), state
- Used by: Orchestrator via `execute()` method

**Bridge Layer (LLM Integration):**
- Purpose: Non-interactive subprocess invocation of `claude --print`
- Location: `flowstate/bridge.py`
- Contains: `ClaudeBridge` class, `BridgeConfig` dataclass, `BridgeResult` dataclass, `_find_claude()` locator
- Supports: `--model`, `--max-budget-usd`, `--effort` overrides; `--allowed-tools` for scoped permissions; `--max-turns` for bounded execution; system prompt injection
- Depends on: subprocess, pathlib, dataclasses
- Used by: All tool adapters via the `.bridge` property on ToolAdapter

**Memory Layer:**
- Purpose: Persistent FTS5 knowledge store with cross-run continuity
- Location: `flowstate/memory.py`
- Contains: `MemoryStore` (SQLite wrapper), `MemoryEntry` (dataclass), `MemoryKind` enum (research/strategy/decision/tool_run/insight), `SearchResult` (score + entry)
- Schema: `memories` table with FTS5 virtual index on summary/content/tags; triggers for auto-index-sync on insert/update/delete
- Search: BM25 ranking via FTS5 porter stemming tokenizer
- Depends on: sqlite3, dataclasses
- Used by: Orchestrator (creates store at pipeline start), tool adapters (call `.get_memory_context(query)` for prior knowledge injection), CLI `memory` commands

**Event System:**
- Purpose: Synchronous event dispatch with priority ordering for step coordination
- Location: `flowstate/events/` — event.py, bus.py, handler.py, registry.py
- Contains:
  - Event base class with Pydantic validation; concrete events (PipelineStarted, StepCompleted, StepFailed, StepStarted, StateChanged, PipelineCompleted)
  - EventBus with priority-ordered dispatch, wildcard handlers, error isolation
  - HandlerRegistry for managing event type → handler[] mapping
  - @handler decorator for automatic registration
- Depends on: pydantic, uuid, datetime
- Used by: Orchestrator emits events; memory_handlers listen and auto-store results

**Config Layer:**
- Purpose: Global configuration persistence (default root directory)
- Location: `flowstate/config.py`
- Contains: `load_default_root()`, `save_default_root()`, `clear_default_root()`, `resolve_root()` (precedence: explicit --root > saved > cwd)
- Depends on: pathlib, tomllib
- Used by: CLI for --root resolution

**Launcher Layer:**
- Purpose: Print native Claude Code commands for session handoff
- Location: `flowstate/launcher.py`
- Contains: `launch_command()` (generates GSD/strategy/research command), `detect_tools()` (checks for .planning/ marker), `print_next_steps()` (suggests actions based on tool availability)
- Depends on: state, pathlib
- Used by: CLI `launch` and `status` commands

## Data Flow

**Pipeline Execution (init phase):**

1. User runs `flowstate init [options]`
2. CLI resolves --root, loads/creates FlowStateModel
3. `run_interview()` prompts for answers, saves to state.interview
4. `write_context_files()` generates 5 files: PROJECT.md, ROADMAP.md, CLAUDE.md, config.json, research/brief.md
5. Orchestrator creates MemoryStore, EventBus; registers memory handlers on bus
6. `run_pipeline()` sequences 5 tools:
   - Research: ResearchAdapter splits topics → one bridge call/topic → merge into research/report.md
   - Strategy: StrategyAdapter single pressure-test call → research/strategy.md
   - GSD: GSDAdapter writes .planning/codebase/ context files (from GSD skills)
   - Discipline: Pure Python audit of git/test/hooks
7. After each step: ToolState updated (status, artifacts, timestamps), state.json persisted
8. On completion: StepCompleted event emitted → memory handlers parse artifacts by `## ` headings → store as individual MemoryEntry records
9. On failure: StepFailed event → error stored as tool_run memory
10. CLI prints next steps (e.g., "flowstate launch gsd 1")

**Phase Execution (run phase):**

1. User runs `flowstate run <N>`
2. CLI loads state, runs `run_phase(N)` in orchestrator
3. Orchestrator looks up phase config in .planning/ROADMAP.md, prints native GSD command
4. User manually invokes that command in Claude Code session

**Memory Injection:**

1. Before each bridge call, adapter calls `get_memory_context(query)` with the research topic
2. MemoryStore.search() runs FTS5 BM25 query with stemming
3. Top-K results (ranked by score, max 1500 tokens) prepended to prompt as `## Prior Knowledge`
4. Ensures compound learning across runs

**State Changed Event Flow:**

1. Any ToolAdapter or CLI command changes state (e.g., setting dry_run, updating tool status)
2. After call completes, `save_state(state, root)` persists flowstate.json
3. StateChanged event emitted (currently unhandled, reserved for future subscribers)

## Key Abstractions

**ToolAdapter:**
- Purpose: Abstract interface for pipeline stage
- Examples: `flowstate/tools/research.py`, `flowstate/tools/strategy.py`, `flowstate/tools/gsd_adapter.py`
- Pattern: Subclass implements `execute()` method returning ToolResult(success, output, artifacts, error); optional bridge and memory injected via constructor; dry-run support via `self.dry_run` flag

**FlowStateModel (Pydantic):**
- Purpose: Typed, validated representation of pipeline state
- Fields: version, created_at, updated_at, interview (InterviewAnswers), preferences (ProjectPreferences), tools (dict[str, ToolState]), artifacts, context_files
- Serialization: model_dump_json() → flowstate.json, load from JSON with backward-compatible migration (v0.1.0 → v0.2.0)

**MemoryEntry:**
- Purpose: Individual searchable fact/finding
- Fields: id, kind (MemoryKind enum), content, summary, source, tags, metadata, created_at, run_id
- Creation: `MemoryEntry.create(kind, content, summary, source=..., tags=...)` → auto-id generation

**Event (Pydantic):**
- Purpose: Immutable, timestamped message through bus
- Fields: event_type, payload (dict), event_id, timestamp, source, metadata
- Subtypes: PipelineStarted, StepCompleted, StepFailed, StateChanged, etc.
- Dispatch: EventBus.emit(event) calls all registered handlers in priority order

## Entry Points

**CLI (`flowstate/cli.py:main()`):**
- Location: Click group decorated with @click.group()
- Triggers: User invokes `flowstate <command>`
- Responsibilities: Option parsing, root resolution, banner printing, delegation to orchestrator or adapters

**Orchestrator (`flowstate/orchestrator.py:run_pipeline()`):**
- Location: Called by CLI `init` command
- Triggers: After interview, or with --skip-interview
- Responsibilities: Sequence research → strategy → gsd → discipline; track state; emit events; inject prior knowledge

**Interview (`flowstate/interview.py:run_interview()`):**
- Location: Called by CLI `init` unless --skip-interview
- Triggers: User runs `flowstate init` without --skip-interview
- Responsibilities: Rich prompt → collect answers into state.interview; validation (e.g., test_coverage as int)

**Bridge (`flowstate/bridge.py:ClaudeBridge.run()`):**
- Location: Called by tool adapters
- Triggers: ResearchAdapter, StrategyAdapter invoke bridge.run(prompt, system_prompt=..., allowed_tools=..., max_turns=...)
- Responsibilities: Subprocess invocation of `claude --print` with args; error handling; timeout enforcement

## Error Handling

**Strategy:** Fail-open — if a tool fails, mark it BLOCKED, emit StepFailed, continue pipeline.

**Patterns:**

- **BridgeResult.success flag:** All bridge.run() calls check `.success` before using `.output`. If false, error logged and step marked BLOCKED with `result.error`.
- **ToolResult.error field:** Adapters return ToolResult with optional error message; orchestrator stores in state.tools[tool].error.
- **Memory storage on failure:** StepFailed event triggers memory handler to store error as `tool_run` kind for later reference.
- **ToolAdapter.run_cmd() catches:**
  - FileNotFoundError → "Command not found" error
  - subprocess.TimeoutExpired → "Command timed out" error
  - All return ToolResult(success=False, error=msg)
- **EventBus error isolation:** If a handler raises, exception caught, error handler called, but other handlers still run.

**State recovery:** flowstate.json persisted after each step, so if pipeline crashes, state is preserved for re-run.

## Cross-Cutting Concerns

**Logging:** Rich console output for user visibility; no file logging. `logger = logging.getLogger(__name__)` in event bus for exception logging.

**Validation:** Pydantic models enforce schema (e.g., test_coverage must be int, ToolStatus must be enum). Interview prompts validate input types (IntPrompt for percentages, Prompt for strings).

**Authentication:** Claude CLI invocation inherits user's Anthropic credentials (no explicit auth in FlowState code); BridgeConfig supports model/budget/effort overrides to control cost/latency.

**Dry-run:** `state.preferences.dry_run` flag checked at orchestrator level; if True, bridge returns synthetic output without subprocess. All adapters respect dry_run via ToolAdapter.dry_run property.

**Memory injection:** Before bridge calls, adapter calls `get_memory_context(topic)` and prepends results to prompt. If memory store is None (or query returns nothing), empty string used (graceful fallback).

**Default root resolution:** `resolve_root(root_option, option_was_explicit=True|False)` implements precedence: explicit --root > saved ~/.config/flowstate/config.toml > cwd. Prevents accidental wrong-project execution.

---

*Architecture analysis: 2026-05-25*
