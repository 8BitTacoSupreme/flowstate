# Phase 6: Run Journal — Pattern Map

**Mapped:** 2026-06-07
**Files analyzed:** 7 (3 new, 4 modified)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `flowstate/journal.py` | service | CRUD | `flowstate/memory.py` (MemoryEntry.create + MemoryStore.add/get_by_kind) | exact |
| `flowstate/memory.py` (add `RUN` to MemoryKind) | model | CRUD | self — extend existing StrEnum | exact |
| `flowstate/orchestrator.py` (call append_run_entry) | orchestrator | request-response | `orchestrator.py:run_pipeline()` L302–312 call-site idiom | exact |
| `flowstate/context_prefix.py` (add since-last-run layer) | utility | transform | `context_prefix.py:build_context_prefix()` L213–217 layer assembly | exact |
| `flowstate/cli.py` (new `journal` command) | controller | request-response | `cli.py:memory_stats` / `memory_search` commands L380–409 | exact |
| `.planning/config.json` (add `run_journal_prefix_entries`) | config | — | `context_prefix.py:_load_budget()` reads `context_prefix_budget_tokens` | exact |
| `tests/test_memory.py`, `tests/test_context_prefix.py`, `tests/test_orchestrator.py`, `tests/test_cli.py` | test | — | existing test files in `tests/` | exact |

---

## Pattern Assignments

### `flowstate/journal.py` (service, CRUD)

**Analog:** `flowstate/memory.py` — MemoryEntry.create(), MemoryStore.add(), MemoryStore.get_by_kind()

**Imports pattern** (`flowstate/memory.py` lines 1–18):
```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import FlowStateModel
```
Note: `journal.py` imports only stdlib + `flowstate.memory` + `flowstate.state`. No bridge import.

**Core pattern — MemoryEntry.create() call** (`flowstate/memory.py` lines 90–111):
```python
@classmethod
def create(
    cls,
    kind: MemoryKind,
    content: str,
    summary: str,
    *,
    source: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    run_id: str = "",
) -> MemoryEntry:
    return cls(
        id=uuid4().hex[:12],
        kind=kind,
        content=content,
        summary=summary,
        source=source,
        tags=tags or [],
        metadata=metadata or {},
        run_id=run_id,
    )
```

**Core pattern — prior-entry fetch before write** (`flowstate/memory.py` lines 248–253):
```python
def get_by_kind(self, kind: MemoryKind, *, limit: int = 20) -> list[MemoryEntry]:
    rows = self._conn.execute(
        "SELECT * FROM memories WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
        (kind.value, limit),
    ).fetchall()
    return [_row_to_entry(row) for row in rows]
```
Call `memory.get_by_kind(MemoryKind.RUN, limit=1)` BEFORE adding the new entry to get the previous run's metadata for diffing.

**Core pattern — add entry** (`flowstate/memory.py` lines 152–169):
```python
def add(self, entry: MemoryEntry) -> str:
    self._conn.execute(
        """INSERT INTO memories (id, kind, content, summary, source, tags, metadata, created_at, run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry.id,
            entry.kind.value,
            entry.content,
            entry.summary,
            entry.source,
            json.dumps(entry.tags),
            json.dumps(entry.metadata),
            entry.created_at.isoformat(),
            entry.run_id,
        ),
    )
    self._conn.commit()
    return entry.id
```

**`append_run_entry` function signature to copy:**
```python
def append_run_entry(
    memory: MemoryStore,
    state: FlowStateModel,
    run_id: str,
    *,
    root: Path,
    dry_run: bool = False,
    timestamp: datetime | None = None,
) -> None:
    """Write one MemoryKind.RUN entry for this run_id (idempotent).

    Fetches the prior RUN entry first to compute the delta. Mirrors to
    .planning/RUNLOG.md as an append-only human-readable trail.
    Never raises — journal failures must not break the pipeline.
    """
```
The `timestamp` parameter is the testability seam (caller can pin it; defaults to `datetime.now(UTC)`).

**Idempotency guard pattern** — check existing RUN entries for this run_id before inserting:
```python
existing = memory.get_by_kind(MemoryKind.RUN, limit=50)
if any(e.run_id == run_id for e in existing):
    return  # already journaled this run
```

**RUNLOG.md append pattern** — mirror entries using `Path.open("a")`:
```python
runlog = root / ".planning" / "RUNLOG.md"
runlog.parent.mkdir(parents=True, exist_ok=True)
with runlog.open("a") as fh:
    fh.write(f"\n## {ts_iso} — run {run_id}\n")
    fh.write(f"- steps: {steps_summary}\n")
    fh.write(f"- artifacts changed: {artifacts_delta}\n")
    fh.write(f"- decisions: (none this phase)\n")
    fh.write(f"- gotchas: (none this phase)\n")
    fh.write(f"- delta: {delta_line}\n")
    if dry_run:
        fh.write("- dry_run: true\n")
```

---

### `flowstate/memory.py` — add `RUN = "run"` to MemoryKind

**Analog:** `flowstate/memory.py` lines 70–75 (self)

**Existing MemoryKind enum** (lines 70–75):
```python
class MemoryKind(StrEnum):
    RESEARCH = "research"
    STRATEGY = "strategy"
    DECISION = "decision"
    TOOL_RUN = "tool_run"
    INSIGHT = "insight"
```

**Target state** — append one line:
```python
class MemoryKind(StrEnum):
    RESEARCH = "research"
    STRATEGY = "strategy"
    DECISION = "decision"
    TOOL_RUN = "tool_run"
    INSIGHT = "insight"
    RUN = "run"
```

---

### `flowstate/orchestrator.py` — call append_run_entry before memory.close()

**Analog:** `flowstate/orchestrator.py` lines 302–318 (the existing `memory.close()` call-site)

**Existing call-site context** (lines 302–318):
```python
    # Step 5: Discipline — pure Python audit
    console.print("\n[bold magenta]5/5 Discipline[/] — audit")
    update_tool(state, "discipline", status=ToolStatus.RUNNING)
    save_state(state, root)

    audit = check_setup(root)
    update_tool(state, "discipline", status=ToolStatus.COMPLETED)
    console.print(f"  [green]{audit.summary}[/green]")
    save_state(state, root)

    memory.close()      # <-- insert append_run_entry call HERE, before this line

    console.print()
    _print_summary(state)
```

**Target insertion** — add between `save_state(state, root)` and `memory.close()`:
```python
    # Journal: write delta entry after all steps complete
    from flowstate.journal import append_run_entry
    try:
        append_run_entry(memory, state, run_id, root=root, dry_run=dry_run)
    except Exception as exc:
        console.print(f"  [yellow]journal: non-fatal error: {exc}[/yellow]")

    memory.close()
```
The `try/except Exception` pattern matches `orchestrator.py` line 217 where context generation failure is caught and logged without aborting.

**`run_id` is already in scope** at `orchestrator.py` line 175:
```python
    run_id = uuid4().hex[:12]
```

---

### `flowstate/context_prefix.py` — add `## Since Last Run` layer

**Analog:** `flowstate/context_prefix.py` lines 213–217 (final assembly idiom)

**Existing layer assembly** (lines 213–217):
```python
    # ── Assemble final string ─────────────────────────────────────────────────
    layers = [fixtures_layer, pack_layer, memory_layer]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
```

**Target state** — add `since_last_run_layer` to the list after `memory_layer`:
```python
    # ── Layer 4: since-last-run (most dynamic — always last) ─────────────────
    since_last_run_layer = _read_since_last_run_layer(root, memory)

    # ── Assemble final string ─────────────────────────────────────────────────
    layers = [fixtures_layer, pack_layer, memory_layer, since_last_run_layer]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
```
The `if layer` filter naturally omits the section when journal is empty — no special casing needed.

**Config read pattern for `run_journal_prefix_entries`** — copy `_load_budget()` exactly (lines 65–81):
```python
def _load_journal_prefix_n(root: Path) -> int:
    """Read run_journal_prefix_entries from .planning/config.json.

    Falls back to 3 when the file is absent, the key is missing,
    or the value is not a positive integer.
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_JOURNAL_PREFIX_N
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("run_journal_prefix_entries")
        if isinstance(value, int) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_JOURNAL_PREFIX_N
```
Where `_DEFAULT_JOURNAL_PREFIX_N = 3` is a module-level constant.

**`_read_since_last_run_layer` private helper** — follows `_read_fixtures_layer` / `_read_pack_layer` pattern (lines 84–113):
```python
def _read_since_last_run_layer(root: Path, memory: Any) -> str:
    """Read last N run-journal entries and format as '## Since Last Run'.

    Returns empty string when the journal is empty (layer omitted silently).
    Never raises. Does NOT import flowstate.bridge.
    """
    try:
        n = _load_journal_prefix_n(root)
        entries = memory.get_by_kind(MemoryKind.RUN, limit=n)
        if not entries:
            return ""
        lines = ["## Since Last Run\n"]
        for entry in entries:
            lines.append(f"### {entry.summary}\n")
            lines.append(entry.content.strip() + "\n\n")
        return "".join(lines).rstrip()
    except Exception:
        return ""
```
Note: import `MemoryKind` from `flowstate.memory` (already imported indirectly via `memory` param).

**Imports to add** — `MemoryKind` import needed at top of `context_prefix.py`:
```python
from flowstate.memory import MemoryKind
```

---

### `flowstate/cli.py` — new `flowstate journal` command

**Analog:** `cli.py` `memory_stats` command (lines 380–409) — same pattern: resolve root, open MemoryStore, render Rich table, close store.

**`memory_stats` command as template** (lines 380–409):
```python
@memory.command("stats")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def memory_stats(root: Path | None):
    """Show memory counts by kind."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    store = MemoryStore(root=root)

    table = Table(title="Memory Stats", border_style="blue")
    table.add_column("Kind", style="bold")
    table.add_column("Count", justify="right")

    total = 0
    for kind in MemoryKind:
        count = store.count(kind)
        total += count
        table.add_row(kind.value, str(count))
    table.add_row("[bold]total[/bold]", f"[bold]{total}[/bold]")

    store.close()
    console.print(table)
```

**Target `journal` command structure** — `@main.command()` (not under `memory` group), with `--limit` and `--root`:
```python
@main.command("journal")
@click.option("--limit", type=int, default=10, help="Max entries to show (default: 10).")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def journal(limit: int, root: Path | None):
    """List recent run-journal entries, newest first."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    try:
        store = MemoryStore(root=root)
        entries = store.get_by_kind(MemoryKind.RUN, limit=limit)
        store.close()
    except Exception:
        console.print("[dim]no journal entries yet[/dim]")
        return

    if not entries:
        console.print("[dim]no journal entries yet[/dim]")
        return

    table = Table(title="Run Journal", border_style="blue")
    table.add_column("Run ID", style="dim", width=12)
    table.add_column("Timestamp", width=24)
    table.add_column("Delta", min_width=40)
    table.add_column("Dry Run", width=8)

    for entry in entries:
        meta = entry.metadata
        table.add_row(
            entry.run_id,
            entry.created_at.isoformat()[:19],
            meta.get("delta_line", entry.summary),
            "yes" if meta.get("dry_run") else "no",
        )

    console.print(table)
```
Key points: `exit 0` on empty journal (return after printing message), `try/except Exception` wraps the MemoryStore open so corrupt DB degrades gracefully.

---

### `.planning/config.json` — add `run_journal_prefix_entries`

**Analog:** existing top-level config keys (`commit_docs`, `parallelization`, etc.) and `_load_budget()` in `context_prefix.py` which reads `context_prefix_budget_tokens`.

**Current top-level structure** (`.planning/config.json` lines 1–7):
```json
{
  "model_profile": "balanced",
  "commit_docs": true,
  "parallelization": true,
  ...
}
```

**Target addition** — add one top-level integer key:
```json
{
  "model_profile": "balanced",
  "commit_docs": true,
  "parallelization": true,
  "run_journal_prefix_entries": 3,
  ...
}
```

---

## Shared Patterns

### `from __future__ import annotations` header
**Source:** Every module in `flowstate/` (e.g., `memory.py` line 8, `context_prefix.py` line 4, `cli.py` line 3)
**Apply to:** `flowstate/journal.py`
```python
from __future__ import annotations
```

### Try/except for non-fatal operations
**Source:** `flowstate/context_prefix.py` lines 74–80 (`_load_budget`) and `orchestrator.py` lines 211–218 (context generation failure):
```python
    try:
        # operation that must not break the pipeline
        ...
    except Exception:
        pass  # or log + return sentinel
```
**Apply to:** `journal.py` (RUNLOG write), `context_prefix.py` (`_read_since_last_run_layer`), `cli.py` (`journal` command MemoryStore open).

### MemoryStore open/close (non-context-manager in CLI)
**Source:** `cli.py` `memory_stats` lines 394–408 — open store, do work, call `store.close()` explicitly (no `with` block in CLI commands):
```python
    store = MemoryStore(root=root)
    # ... work ...
    store.close()
    console.print(table)
```
**Apply to:** `cli.py` `journal` command.

### `resolve_root` + `_root_was_explicit()` in every CLI command
**Source:** `cli.py` every command, e.g. `memory_stats` line 350:
```python
    root = resolve_root(root, option_was_explicit=_root_was_explicit())
```
**Apply to:** `cli.py` `journal` command.

### Layer private helper naming in context_prefix
**Source:** `context_prefix.py` — `_read_fixtures_layer(root)`, `_read_pack_layer(root)` (lines 84–113). Private underscore prefix, returns `str`, returns `""` on any failure or absence.
**Apply to:** `_read_since_last_run_layer(root, memory)` in `context_prefix.py`.

---

## Test Patterns

### `test_memory.py` fixtures to extend
**Source:** `/Users/jhogan/frameworx/tests/test_memory.py` lines 12–19

`store` fixture (lines 12–15):
```python
@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s
```
Extend `test_memory.py` with:
- `test_run_kind_value()` — assert `MemoryKind.RUN == "run"`
- `test_count_by_kind_includes_run()` — assert `store.count(MemoryKind.RUN) == 0` on fresh store
- `test_add_run_entry_and_get_by_kind()` — add a RUN entry, get_by_kind returns it newest-first

### `test_context_prefix.py` patterns to extend
**Source:** `/Users/jhogan/frameworx/tests/test_context_prefix.py` lines 51–55, 63–85

`_make_memory_stub` helper (lines 51–55):
```python
def _make_memory_stub(returns: str = "") -> MagicMock:
    """Return a mock MemoryStore whose get_context returns the given string."""
    mem = MagicMock()
    mem.get_context.return_value = returns
    return mem
```
Extend to also stub `get_by_kind`:
```python
def _make_memory_stub(returns: str = "", run_entries=None) -> MagicMock:
    mem = MagicMock()
    mem.get_context.return_value = returns
    mem.get_by_kind.return_value = run_entries or []
    return mem
```
New test cases needed:
- `test_since_last_run_omitted_when_empty()` — empty `get_by_kind` → `## Since Last Run` absent
- `test_since_last_run_present_when_populated()` — 1 entry → heading appears, after `## Prior Knowledge`
- `test_since_last_run_respects_limit_from_config()` — write config with N=2, add 5 entries, assert `get_by_kind` called with `limit=2`
- `test_since_last_run_after_memory_layer()` — ordering check: `## Since Last Run` index > `## Prior Knowledge` index
- `test_no_bridge_import_in_context_prefix()` — already exists, passes through unchanged

### `test_orchestrator.py` patterns to extend
**Source:** `/Users/jhogan/frameworx/tests/test_orchestrator.py` lines 9–37

`test_dry_run_pipeline` pattern (lines 9–36) — extend with:
```python
def test_run_pipeline_writes_run_journal_entry(tmp_path: Path):
    """append_run_entry must be called once per pipeline run."""
    from unittest.mock import patch
    from flowstate.state import FlowStateModel

    state = FlowStateModel()
    state.preferences.dry_run = True

    with patch("flowstate.orchestrator.append_run_entry") as mock_journal:
        run_pipeline(state, tmp_path)

    assert mock_journal.call_count == 1
    _, kwargs = mock_journal.call_args
    # run_id must be a 12-char hex string
    assert len(mock_journal.call_args.args[2]) == 12
```

### `test_cli.py` patterns to extend
**Source:** `/Users/jhogan/frameworx/tests/test_cli.py` lines 1–10, `_isolate_config` fixture lines 16–22

`CliRunner` invocation pattern (implicit in existing tests):
```python
runner = CliRunner()
result = runner.invoke(main, ["journal", "--root", str(tmp_path)])
assert result.exit_code == 0
assert "no journal entries yet" in result.output
```

New test cases needed:
- `test_journal_empty_exits_zero()` — fresh store → exit 0 + "no journal entries yet"
- `test_journal_populated_shows_table()` — add 2 RUN entries to store, invoke → table output contains run IDs
- `test_journal_limit_option()` — add 5 entries, `--limit 2` → only 2 rows in output
- `test_journal_corrupt_db_exits_zero()` — write a non-SQLite file as `memory.db` → exit 0 (graceful degrade)

---

## No Analog Found

All files in this phase have close analogs in the codebase. No file requires falling back to RESEARCH.md patterns.

---

## Metadata

**Analog search scope:** `/Users/jhogan/frameworx/flowstate/`, `/Users/jhogan/frameworx/tests/`
**Files scanned:** 8 source files, 4 test files
**Pattern extraction date:** 2026-06-07
