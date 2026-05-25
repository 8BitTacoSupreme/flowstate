<!-- GSD:project-start source:PROJECT.md -->
## Project

**FlowState**

FlowState is a CLI-first context orchestrator that scaffolds agentic-framework projects (GSD and friends) — it runs a deterministic 5-step pipeline (Context Generation → Research → Strategy → GSD → Discipline), wraps `claude --print` for scoped LLM calls with budget/model overrides, and persists a searchable SQLite FTS5 memory across runs.

Lives at `/Users/jhogan/frameworx`, package `flowstate`, Python 3.12+, Flox-managed env, Claude Code CLI as the LLM bridge.

**Core Value:** **Each run starts smarter than the last** — the pipeline produces durable artifacts (PROJECT.md, ROADMAP.md, research/, memory.db) and auto-injects prior findings into subsequent runs, so the work compounds instead of repeating.

If everything else fails, that compounding loop is what FlowState exists to deliver.

### Constraints

- **Tech stack:** Python 3.12+, Click for CLI, Pydantic for state, SQLite + FTS5 for memory, subprocess for the Claude bridge. No new runtime dependencies in this milestone.
- **Coverage:** ≥80% enforced by `pyproject.toml` (`--cov-fail-under=80`). Pre-commit runs ruff (legacy + format), trailing-whitespace, EOF, large-file, merge-conflict, debug-statement checks.
- **Bridge:** Claude Code CLI v2+ must be locatable; FlowState invokes `claude --print` non-interactively. No direct Anthropic API calls.
- **Compatibility:** State migration must work from v0.1.0 → v0.2.0 → v0.3.0 (this milestone bumps minor).
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12+ - All source code in `flowstate/`, tests in `tests/`
- YAML - Configuration (`pyproject.toml`, `.pre-commit-config.yaml`)
- SQL - Schema and queries in `flowstate/memory.py` (SQLite with FTS5 virtual tables)
## Runtime
- Python 3.12+ (specified in `pyproject.toml` and `uv.lock`)
- SQLite 3 - Bundled with Python, used for persistent memory store
- `uv` - Modern Python package manager (lockfile: `uv.lock`)
- Entry point: `flowstate = "flowstate.cli:main"` (defined in `pyproject.toml`)
## Frameworks
- `click>=8.1` - CLI framework for command/group structure (`flowstate/cli.py`)
- `pydantic>=2.0` - Data validation and configuration models (`flowstate/state.py`)
- `rich>=13.0` - Terminal UI rendering (tables, panels, formatting in `flowstate/cli.py`)
- `pytest>=9.0` - Test runner
- `pytest-cov>=7.0` - Coverage reporting (80% minimum enforced)
- `ruff>=0.15` - Linter and formatter (configured in `pyproject.toml`)
- `pre-commit>=4.0` - Git hooks for linting, formatting, and coverage checks (`.pre-commit-config.yaml`)
- `hatchling` - Build backend (specified in `pyproject.toml`)
## Key Dependencies
- `sqlite-vec>=0.1.6` - Vector storage extension for SQLite FTS5 (used in `flowstate/memory.py` for semantic search)
- `click` - Powers all CLI commands and options
- `pydantic` - Powers type-safe state models and validation
- `rich` - Provides styled console output (tables, panels, colors)
- `pre-commit` - Enforces code quality before commits (linting, formatting, coverage gates)
- `coverage` - Measures test coverage; fail if below 80%
## Configuration
- `.env` file (local, not committed) - Stores EXA_API_KEY for semantic search
- `.env.example` - Template showing required variables
- `~/.config/flowstate/config.toml` - Persistent user config (default project root)
- `pyproject.toml` - Single source of truth for dependencies, version, entry points, tool configs
- `uv.lock` - Locked dependency tree (production-ready pinning)
- `.pre-commit-config.yaml` - Git hook definitions (Ruff, pytest-cov, trailing-whitespace)
## Platform Requirements
- macOS/Linux/Windows with Python 3.12+
- `uv` package manager for dependency isolation
- Flox environment (optional, for reproducibility)
- Git (required for pre-commit hooks)
- Python 3.12+ runtime
- SQLite 3 (bundled with Python)
- `claude` CLI binary available in PATH or via `FLOWSTATE_CLAUDE_BIN` env var
- Terminal with 80+ character width (for Rich formatting)
## Tooling
- Ruff (linting + formatting): python style check and auto-fix
- pytest runs on every `git push` (pre-commit hook)
- Minimum coverage: 80% (coverage report: `htmlcov/index.html`)
- Command: `python -m pytest tests/ --cov=flowstate --cov-fail-under=80`
- Pre-commit hooks enforce: Ruff check/format → pytest with coverage → standard checks (trailing whitespace, EOF fixer, YAML validation, merge conflict detection)
- Non-blocking before commit; blocking before push (pytest-cov)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Lowercase snake_case: `flowstate.py`, `memory_handlers.py`, `test_config.py`
- Module names are descriptive and map to functional domains: `cli.py`, `memory.py`, `orchestrator.py`, `bridge.py`
- Test files follow pattern `test_<module>.py` (e.g., `test_memory.py` tests `memory.py`)
- Private/internal modules use leading underscore in functions/helpers: `_migrate_state()`, `_find_claude()`, `_has_python_package()`
- Lowercase snake_case: `load_state()`, `save_state()`, `check_setup()`, `resolve_root()`
- Descriptive verb-first: `run_pipeline()`, `update_tool()`, `write_context_files()`, `create_memory_handlers()`
- Private functions prefixed with `_`: `_migrate_state()`, `_sanitize_fts_query()`, `_run_step()`, `_row_to_entry()`
- Boolean-returning functions often use `is_`/`has_` prefix: `available` (property), `exists()` (Path method)
- Lowercase snake_case throughout: `tmp_path`, `dry_run`, `memory_store`, `event_bus`
- Constant-like module-level strings: `BANNER`, `STATE_FILE`, `_FRESH_TARGETS`, `TOOL_ORDER`, `STEP_LABELS`, `STEP_STYLES`
- Enum values using uppercase in class definition: `READY`, `RUNNING`, `COMPLETED`, `BLOCKED` (StrEnum)
- Private class-level variables use underscore: `_conn` in MemoryStore
- PEP 484 union syntax with `|` (requires `from __future__ import annotations`): `root: Path | None`, `status: ToolStatus | None`
- Dataclass and Pydantic fields use proper type hints: `created_at: datetime`, `artifacts: list[str]`, `metadata: dict[str, Any]`
- Optional fields default to `None`: `error: str | None = None`, `completed_at: datetime | None = None`
- Generic collections: `list[str]`, `dict[str, bool]`, `dict[str, Any]`
## Code Style
- Tool: `ruff format`
- Line length: 100 characters (see `pyproject.toml` `line-length = 100`)
- Quote style: Double quotes (enforced by `ruff-format` with `quote-style = "double"`)
- Indentation: 4 spaces (default Python, enforced by `indent-style = "space"`)
- Tool: `ruff` with comprehensive rule set
- Selected rules: `E`, `W` (pycodestyle), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (flake8-bugbear), `SIM` (flake8-simplify), `RUF` (ruff-specific)
- Ignored: `E501` (line too long — handled by formatter)
- Disabled: `TCH` (false positives with `from __future__ import annotations`)
- Runs automatically in pre-commit hook
## Import Organization
## Error Handling
- Explicit exception catching: `try: ... except FileNotFoundError: ...` (see `bridge.py` line 124-125)
- Broad exception catching for config loading: `try: ... except Exception: return None` (see `config.py` line 20-23) — tolerates any parse failure and returns None as sentinel
- No custom exception classes; use standard library exceptions (FileNotFoundError, TimeoutExpired, etc.)
- Result objects with success flag for non-critical failures: `BridgeResult(success=False, output="", error="...")` instead of raising
- Silent failure for stale/missing config: `load_default_root()` returns `None` if path doesn't exist on disk
## Logging
- No debug/info/warning levels — everything goes to stdout via Console
- Rich markup for color/styling: `[green]`, `[red]`, `[dim]`, `[bold]`, `[cyan]`, `[yellow]`, `[magenta]`
- Panels and Tables for structured UI (see `cli.py` for examples)
- No file logging; all output is ephemeral to terminal
## Comments
- Docstrings on all public functions (see `memory.py._sanitize_fts_query()`)
- Inline comments for non-obvious logic: `# Check if --root was passed on the command line` (cli.py line 31)
- SQL/regex comments explaining complex queries: `-- Escape a raw string for FTS5 MATCH` (memory.py line 195)
- TODO/FIXME sparse; codebase uses markers for intentional deferred work (grepped 0 TODOs in source)
## Function Design
- Most functions 1–50 lines (see `config.py` functions 12–30 lines each)
- Larger orchestration functions up to 100 lines (e.g., `orchestrator.py:run_pipeline()` at 150+ lines for clarity in one place)
- Positional parameters for required inputs: `root: Path`, `tool: str`
- Keyword-only parameters (`*`) for optional/boolean flags: `root: Path | None = None`, `status: ToolStatus | None = None` (see `state.py:update_tool()`)
- Defaults as None or False; never mutable defaults
- Functions return typed values: `-> Path`, `-> FlowStateModel`, `-> list[SearchResult]`
- Void functions use no explicit return: `def close(self) -> None:`
- Context managers implement `__enter__` and `__exit__`: `MemoryStore` (memory.py line 146–150)
## Module Design
- No `__init__.py` star imports; version only: `flowstate/__init__.py` exports `__version__`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **CLI-first:** 8 Click commands (init, status, launch, run, context, memory, check, fresh, config)
- **Non-interactive bridge:** Wraps `claude --print` with scoped tool permissions and budget/model overrides
- **Pure Python where possible:** Context generation, discipline audit, memory store are not LLM-dependent
- **Adapter pattern:** Each tool (research, strategy, gsd, discipline) is a pluggable ToolAdapter subclass
- **Event-driven coordination:** StepCompleted/StepFailed events trigger memory handlers for auto-storage
- **Stateful:** flowstate.json tracks each tool's status (Ready/Running/Completed/Blocked), artifacts, timestamps
## Layers
- Purpose: User-facing commands and option parsing
- Location: `flowstate/cli.py`
- Contains: 8 Click command groups (main, memory, config) with option handling for dry-run, model override, budget override
- Depends on: config, state, orchestrator, interview, launcher, memory, bridge, discipline, context
- Used by: End users via `flowstate init|status|launch|run|context|memory|check|fresh|config`
- Purpose: Persistence and validation of pipeline state
- Location: `flowstate/state.py`
- Contains: Pydantic models (FlowStateModel, ToolState, InterviewAnswers, ProjectPreferences) and load/save/migrate functions
- Depends on: pydantic, pathlib
- Used by: Orchestrator, CLI, all adapters; calls `load_state()` and `save_state()` after each pipeline step
- Purpose: Sequences the 5-step pipeline and coordinates tool execution
- Location: `flowstate/orchestrator.py`
- Contains: `run_pipeline()` (main entry), `run_phase()` (single GSD phase), `print_status()` (table output), `_run_step()` (generic step runner with status/artifact tracking), `_make_bridge()` (bridge config builder)
- Depends on: state, bridge, context, all tool adapters, memory, events
- Used by: CLI commands `init`, `run`, `status`
- Purpose: Interactive intake questionnaire for problem/vision/milestones
- Location: `flowstate/interview.py`
- Contains: `run_interview()` (main loop), section definitions (research, strategy, management, discipline) with custom prompt per section
- Depends on: rich, state
- Used by: CLI `init` command when `--skip-interview` is not set
- Purpose: Deterministic, non-LLM file generation from interview answers
- Location: `flowstate/context.py`
- Contains: Template functions `generate_project_md()`, `generate_roadmap_md()`, `generate_gsd_config()`, `generate_claude_md()` that produce JSON/Markdown consumed by downstream tools
- Depends on: state, textwrap (no LLM)
- Used by: Orchestrator during pipeline, CLI `context` command for regeneration
- Purpose: Pluggable interface for each stage (research, strategy, gsd, discipline)
- Location: `flowstate/tools/` — base.py, research.py, strategy.py, gsd_adapter.py
- Contains:
- Depends on: bridge, memory (optional), state
- Used by: Orchestrator via `execute()` method
- Purpose: Non-interactive subprocess invocation of `claude --print`
- Location: `flowstate/bridge.py`
- Contains: `ClaudeBridge` class, `BridgeConfig` dataclass, `BridgeResult` dataclass, `_find_claude()` locator
- Supports: `--model`, `--max-budget-usd`, `--effort` overrides; `--allowed-tools` for scoped permissions; `--max-turns` for bounded execution; system prompt injection
- Depends on: subprocess, pathlib, dataclasses
- Used by: All tool adapters via the `.bridge` property on ToolAdapter
- Purpose: Persistent FTS5 knowledge store with cross-run continuity
- Location: `flowstate/memory.py`
- Contains: `MemoryStore` (SQLite wrapper), `MemoryEntry` (dataclass), `MemoryKind` enum (research/strategy/decision/tool_run/insight), `SearchResult` (score + entry)
- Schema: `memories` table with FTS5 virtual index on summary/content/tags; triggers for auto-index-sync on insert/update/delete
- Search: BM25 ranking via FTS5 porter stemming tokenizer
- Depends on: sqlite3, dataclasses
- Used by: Orchestrator (creates store at pipeline start), tool adapters (call `.get_memory_context(query)` for prior knowledge injection), CLI `memory` commands
- Purpose: Synchronous event dispatch with priority ordering for step coordination
- Location: `flowstate/events/` — event.py, bus.py, handler.py, registry.py
- Contains:
- Depends on: pydantic, uuid, datetime
- Used by: Orchestrator emits events; memory_handlers listen and auto-store results
- Purpose: Global configuration persistence (default root directory)
- Location: `flowstate/config.py`
- Contains: `load_default_root()`, `save_default_root()`, `clear_default_root()`, `resolve_root()` (precedence: explicit --root > saved > cwd)
- Depends on: pathlib, tomllib
- Used by: CLI for --root resolution
- Purpose: Print native Claude Code commands for session handoff
- Location: `flowstate/launcher.py`
- Contains: `launch_command()` (generates GSD/strategy/research command), `detect_tools()` (checks for .planning/ marker), `print_next_steps()` (suggests actions based on tool availability)
- Depends on: state, pathlib
- Used by: CLI `launch` and `status` commands
## Data Flow
## Key Abstractions
- Purpose: Abstract interface for pipeline stage
- Examples: `flowstate/tools/research.py`, `flowstate/tools/strategy.py`, `flowstate/tools/gsd_adapter.py`
- Pattern: Subclass implements `execute()` method returning ToolResult(success, output, artifacts, error); optional bridge and memory injected via constructor; dry-run support via `self.dry_run` flag
- Purpose: Typed, validated representation of pipeline state
- Fields: version, created_at, updated_at, interview (InterviewAnswers), preferences (ProjectPreferences), tools (dict[str, ToolState]), artifacts, context_files
- Serialization: model_dump_json() → flowstate.json, load from JSON with backward-compatible migration (v0.1.0 → v0.2.0)
- Purpose: Individual searchable fact/finding
- Fields: id, kind (MemoryKind enum), content, summary, source, tags, metadata, created_at, run_id
- Creation: `MemoryEntry.create(kind, content, summary, source=..., tags=...)` → auto-id generation
- Purpose: Immutable, timestamped message through bus
- Fields: event_type, payload (dict), event_id, timestamp, source, metadata
- Subtypes: PipelineStarted, StepCompleted, StepFailed, StateChanged, etc.
- Dispatch: EventBus.emit(event) calls all registered handlers in priority order
## Entry Points
- Location: Click group decorated with @click.group()
- Triggers: User invokes `flowstate <command>`
- Responsibilities: Option parsing, root resolution, banner printing, delegation to orchestrator or adapters
- Location: Called by CLI `init` command
- Triggers: After interview, or with --skip-interview
- Responsibilities: Sequence research → strategy → gsd → discipline; track state; emit events; inject prior knowledge
- Location: Called by CLI `init` unless --skip-interview
- Triggers: User runs `flowstate init` without --skip-interview
- Responsibilities: Rich prompt → collect answers into state.interview; validation (e.g., test_coverage as int)
- Location: Called by tool adapters
- Triggers: ResearchAdapter, StrategyAdapter invoke bridge.run(prompt, system_prompt=..., allowed_tools=..., max_turns=...)
- Responsibilities: Subprocess invocation of `claude --print` with args; error handling; timeout enforcement
## Error Handling
- **BridgeResult.success flag:** All bridge.run() calls check `.success` before using `.output`. If false, error logged and step marked BLOCKED with `result.error`.
- **ToolResult.error field:** Adapters return ToolResult with optional error message; orchestrator stores in state.tools[tool].error.
- **Memory storage on failure:** StepFailed event triggers memory handler to store error as `tool_run` kind for later reference.
- **ToolAdapter.run_cmd() catches:**
- **EventBus error isolation:** If a handler raises, exception caught, error handler called, but other handlers still run.
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
