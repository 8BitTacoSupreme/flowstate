# External Integrations

**Analysis Date:** 2026-05-25

## APIs & External Services

**Semantic Search:**
- **Exa** - Semantic search API (exa.ai)
  - SDK/Client: MCP server interface
  - Auth: `EXA_API_KEY` (env var, defined in `.env.example`)
  - Usage: Optional integration for research workflows

**Code Execution:**
- **Claude CLI** - Anthropic's Claude Code runtime bridge
  - Binary: `claude` (expected in PATH or `FLOWSTATE_CLAUDE_BIN` env var)
  - Integration: `flowstate/bridge.py` wraps `claude --print` for non-interactive execution
  - Features: Prompt execution, tool permissions, model selection, budget controls

## Data Storage

**Databases:**
- **SQLite 3** - Local persistent memory store
  - Path: `memory.db` (created at project root on first run)
  - Client: Native Python `sqlite3` module (no ORM)
  - Schema: `SCHEMA_SQL` in `flowstate/memory.py` (v1)
  - Indexes: `idx_memories_kind`, `idx_memories_run_id`, `idx_memories_created_at`

**File Storage:**
- Local filesystem only - Projects store state files in `.planning/`, `flowstate.json`, context files
- No cloud storage integration

**Caching:**
- In-memory during session (via `ClaudeBridge` result caching possible in future)
- SQLite FTS5 provides query-result caching implicitly

## Authentication & Identity

**Auth Provider:**
- Custom - FlowState does not authenticate end users
- API Keys: Only `EXA_API_KEY` required (optional)
- No OAuth, no user accounts

## Monitoring & Observability

**Error Tracking:**
- None integrated (all errors logged to console via `rich`)

**Logs:**
- Console only - `rich.console.Console` for structured output (no file logging)
- Levels: Info (standard output), error (stderr via console)
- Context: `flowstate/cli.py` prints status, progress, and diagnostics

## CI/CD & Deployment

**Hosting:**
- None - FlowState is a local CLI tool
- No remote deployment

**CI Pipeline:**
- Local pre-commit hooks (no remote CI)
- Git hooks run: Ruff (lint/format) → pytest (80% coverage check) before push

## Environment Configuration

**Required env vars:**
- `FLOWSTATE_CLAUDE_BIN` (optional) - Path to `claude` CLI if not in PATH

**Optional env vars:**
- `EXA_API_KEY` - Exa semantic search API key (if using research integration)

**Secrets location:**
- `.env` (local, not committed) - User-provided API keys
- Git-ignored to prevent accidental commits

## Webhooks & Callbacks

**Incoming:**
- None (local CLI only)

**Outgoing:**
- None currently implemented

## Claude CLI Bridge Integration

**Purpose:**
- Hands off orchestration tasks to Claude Code agents (GSD, research, strategy tools)

**Invocation Pattern:**
- `ClaudeBridge.run(prompt, system_prompt, allowed_tools, model, budget)`
- Subprocess call to `claude --print [options] "prompt text"`
- Configuration: `BridgeConfig` in `flowstate/bridge.py`
  - `timeout`: Default 300s per call
  - `max_turns`: Default 10 agentic turns
  - `model`: Configurable (default from env or arg)
  - `max_budget_usd`: Optional spend limit

**Tool Permissions:**
- Passed as `allowed_tools` list (e.g., `["Read", "Bash(git:*)", "Edit"]`)
- Whitelist-based access control for security

## Memory Store Integration

**Technology:**
- SQLite FTS5 (Full-Text Search) with BM25 ranking
- Tokenizer: Porter stemming + Unicode61
- Virtual table: `memories_fts` (mirrored from `memories` base table via triggers)

**Usage Pattern:**
- `MemoryStore` class in `flowstate/memory.py`
- Context manager: `with MemoryStore(root) as store:`
- Methods: `add()`, `add_many()`, `search()`, `get()`, `get_by_kind()`, `get_context()`, `clear()`, `count()`
- Exported via CLI: `flowstate memory search`, `flowstate memory stats`, `flowstate memory clear`

**Memory Types:**
- `RESEARCH` - Findings from semantic search
- `STRATEGY` - Planning decisions
- `DECISION` - Project direction choices
- `TOOL_RUN` - Execution context from tool invocations
- `INSIGHT` - Derived or synthesized knowledge

---

*Integration audit: 2026-05-25*
