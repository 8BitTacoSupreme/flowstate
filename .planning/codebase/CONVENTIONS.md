# Coding Conventions

**Analysis Date:** 2025-05-25

## Naming Patterns

**Files:**
- Lowercase snake_case: `flowstate.py`, `memory_handlers.py`, `test_config.py`
- Module names are descriptive and map to functional domains: `cli.py`, `memory.py`, `orchestrator.py`, `bridge.py`
- Test files follow pattern `test_<module>.py` (e.g., `test_memory.py` tests `memory.py`)
- Private/internal modules use leading underscore in functions/helpers: `_migrate_state()`, `_find_claude()`, `_has_python_package()`

**Functions:**
- Lowercase snake_case: `load_state()`, `save_state()`, `check_setup()`, `resolve_root()`
- Descriptive verb-first: `run_pipeline()`, `update_tool()`, `write_context_files()`, `create_memory_handlers()`
- Private functions prefixed with `_`: `_migrate_state()`, `_sanitize_fts_query()`, `_run_step()`, `_row_to_entry()`
- Boolean-returning functions often use `is_`/`has_` prefix: `available` (property), `exists()` (Path method)

**Variables:**
- Lowercase snake_case throughout: `tmp_path`, `dry_run`, `memory_store`, `event_bus`
- Constant-like module-level strings: `BANNER`, `STATE_FILE`, `_FRESH_TARGETS`, `TOOL_ORDER`, `STEP_LABELS`, `STEP_STYLES`
- Enum values using uppercase in class definition: `READY`, `RUNNING`, `COMPLETED`, `BLOCKED` (StrEnum)
- Private class-level variables use underscore: `_conn` in MemoryStore

**Types:**
- PEP 484 union syntax with `|` (requires `from __future__ import annotations`): `root: Path | None`, `status: ToolStatus | None`
- Dataclass and Pydantic fields use proper type hints: `created_at: datetime`, `artifacts: list[str]`, `metadata: dict[str, Any]`
- Optional fields default to `None`: `error: str | None = None`, `completed_at: datetime | None = None`
- Generic collections: `list[str]`, `dict[str, bool]`, `dict[str, Any]`

## Code Style

**Formatting:**
- Tool: `ruff format`
- Line length: 100 characters (see `pyproject.toml` `line-length = 100`)
- Quote style: Double quotes (enforced by `ruff-format` with `quote-style = "double"`)
- Indentation: 4 spaces (default Python, enforced by `indent-style = "space"`)

**Linting:**
- Tool: `ruff` with comprehensive rule set
- Selected rules: `E`, `W` (pycodestyle), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (flake8-bugbear), `SIM` (flake8-simplify), `RUF` (ruff-specific)
- Ignored: `E501` (line too long — handled by formatter)
- Disabled: `TCH` (false positives with `from __future__ import annotations`)
- Runs automatically in pre-commit hook

**File Header:**
```python
"""Module docstring — one-line description of purpose."""

from __future__ import annotations
```

All modules use `from __future__ import annotations` for PEP 563 forward references (enables `Path | None` syntax without runtime overhead).

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, allows `|` union syntax)
2. Standard library (stdlib): `from pathlib import Path`, `from datetime import datetime`, `import json`, `import sqlite3`
3. Third-party: `import click`, `from pydantic import BaseModel`, `from rich.console import Console`
4. Flowstate local: `from flowstate.state import FlowStateModel`, `from flowstate.memory import MemoryStore`

**Path Aliases:**
```toml
# pyproject.toml
[tool.ruff.lint.isort]
known-first-party = ["flowstate"]
```
Enforced via isort in ruff. All flowstate imports use absolute paths from `flowstate` package root (e.g., `from flowstate.memory import MemoryEntry`).

**Module Exports:**
Modules do not use `__all__`. Everything importable is explicitly named at call sites.

## Error Handling

**Patterns:**
- Explicit exception catching: `try: ... except FileNotFoundError: ...` (see `bridge.py` line 124-125)
- Broad exception catching for config loading: `try: ... except Exception: return None` (see `config.py` line 20-23) — tolerates any parse failure and returns None as sentinel
- No custom exception classes; use standard library exceptions (FileNotFoundError, TimeoutExpired, etc.)
- Result objects with success flag for non-critical failures: `BridgeResult(success=False, output="", error="...")` instead of raising
- Silent failure for stale/missing config: `load_default_root()` returns `None` if path doesn't exist on disk

**Success/Failure Results:**
Use result dataclasses to represent operation outcomes:
```python
@dataclass
class BridgeResult:
    success: bool
    output: str
    exit_code: int = 0
    error: str | None = None
```

## Logging

**Framework:** No structured logging library. Uses print via `rich.console.Console` for user output.

**Patterns:**
```python
from rich.console import Console
console = Console()

# Status output
console.print(f"  [green]Success[/green]")
console.print(f"  [red]Failed: {error}[/red]")
console.print("[dim]Subtle info[/dim]")

# Structured output
console.print(Panel(..., border_style="blue"))
console.print(Table(...))
```

- No debug/info/warning levels — everything goes to stdout via Console
- Rich markup for color/styling: `[green]`, `[red]`, `[dim]`, `[bold]`, `[cyan]`, `[yellow]`, `[magenta]`
- Panels and Tables for structured UI (see `cli.py` for examples)
- No file logging; all output is ephemeral to terminal

## Comments

**When to Comment:**
- Docstrings on all public functions (see `memory.py._sanitize_fts_query()`)
- Inline comments for non-obvious logic: `# Check if --root was passed on the command line` (cli.py line 31)
- SQL/regex comments explaining complex queries: `-- Escape a raw string for FTS5 MATCH` (memory.py line 195)
- TODO/FIXME sparse; codebase uses markers for intentional deferred work (grepped 0 TODOs in source)

**Docstring Style:**
Short one-liner at top of function, no formal param/return blocks:
```python
def _sanitize_fts_query(query: str) -> str:
    """Escape a raw string for FTS5 MATCH.

    FTS5 interprets bare words as column names if they match a column,
    and operators like AND/OR/NOT/NEAR have special meaning.  Wrapping
    each token in double-quotes forces literal matching.
    """
```

Module-level docstrings describe purpose and key context:
```python
"""Persistent memory store backed by SQLite FTS5.

Provides cross-run continuity for FlowState pipelines. Research findings,
strategy decisions, and failure context are stored and searchable via
full-text search with BM25 ranking.
"""
```

## Function Design

**Size:**
- Most functions 1–50 lines (see `config.py` functions 12–30 lines each)
- Larger orchestration functions up to 100 lines (e.g., `orchestrator.py:run_pipeline()` at 150+ lines for clarity in one place)

**Parameters:**
- Positional parameters for required inputs: `root: Path`, `tool: str`
- Keyword-only parameters (`*`) for optional/boolean flags: `root: Path | None = None`, `status: ToolStatus | None = None` (see `state.py:update_tool()`)
- Defaults as None or False; never mutable defaults

**Return Values:**
- Functions return typed values: `-> Path`, `-> FlowStateModel`, `-> list[SearchResult]`
- Void functions use no explicit return: `def close(self) -> None:`
- Context managers implement `__enter__` and `__exit__`: `MemoryStore` (memory.py line 146–150)

## Module Design

**Exports:**
Classes and functions at module level are public. Private helpers use leading `_`.

**Barrel Files:**
- No `__init__.py` star imports; version only: `flowstate/__init__.py` exports `__version__`

**Dataclasses:**
Used for immutable/structured data:
```python
@dataclass
class MemoryEntry:
    id: str
    kind: MemoryKind
    content: str
    ...
    @classmethod
    def create(...) -> MemoryEntry:  # Factory method
```

**Pydantic Models:**
Used for validated state/config:
```python
class FlowStateModel(BaseModel):
    version: str = "0.2.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ...
```

**StrEnum:**
Used for string constants with type safety:
```python
class ToolStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
```

---

*Convention analysis: 2025-05-25*
