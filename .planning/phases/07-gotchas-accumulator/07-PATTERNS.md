# Phase 7: Gotchas Accumulator — Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 9 (2 new, 7 modified)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `flowstate/gotchas.py` | service/utility | CRUD + file-I/O | `flowstate/journal.py` | role-match (pure-Python, MemoryStore, mirror-file, never-raises) |
| `flowstate/memory.py` | service | CRUD | self (add L153-170) | exact (add `update()` mirroring `add()`) |
| `flowstate/context_prefix.py` | utility | transform | self (_read_since_last_run_layer L107-124, assembly L210-284) | exact (insert gotchas layer using same integration pattern) |
| `flowstate/memory_handlers.py` | middleware/handler | event-driven | self (on_step_failed L104-119) | exact (extend handler; keep existing, add alongside) |
| `flowstate/cli.py` — `gotchas` command | controller | request-response | `flowstate/cli.py` journal command (L550-593) | exact clone |
| `flowstate/journal.py` | service | CRUD + file-I/O | self (append_run_entry) | exact (populate gotchas metadata slot) |
| `flowstate/orchestrator.py` | orchestrator | event-driven | self (append_run_entry call at L313-317) | exact (add harvest call at same pattern site) |
| `tests/test_gotchas.py` | test | — | `tests/test_journal.py` | exact |
| `tests/test_context_prefix.py` | test | — | self (TestSinceLastRunLayer pattern) | exact |

---

## Pattern Assignments

### `flowstate/gotchas.py` (service, CRUD + file-I/O)

**Analog:** `flowstate/journal.py` (full file)

**Imports pattern** (journal.py L1-15):
```python
"""Run-journal writer — pure-Python, no bridge/LLM dependency."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import FlowStateModel
```
Gotchas imports will be similar; replace `FlowStateModel` with `Diagnosis` from `flowstate.doctor`. NO `flowstate.bridge` import.

**Core function signature pattern** (journal.py L18-26):
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
```
`capture_gotcha` mirrors this shape:
```python
def capture_gotcha(
    memory: MemoryStore,
    *,
    source: str,
    message: str,
    root: Path,
    severity: str = "warning",
    run_id: str = "",
    timestamp: datetime | None = None,
) -> None:
```

**Never-raises + try/except contract** (journal.py L110-113 and L146-163):
```python
    try:
        memory.add(entry)
    except Exception:
        return  # memory write failed; best-effort — never raise into pipeline

    # Mirror to GOTCHAS.md — swallow any write errors
    _rewrite_gotchas_md(root, ...)

def _append_runlog(...) -> None:
    """Append a section to .planning/RUNLOG.md. Never raises."""
    try:
        ...
        with runlog.open("a") as fh:
            ...
    except Exception:
        pass  # journal failure must never break the pipeline
```
Apply the same pattern for `_rewrite_gotchas_md` — catch all exceptions, pass.

**Idempotency guard pattern** (journal.py L35-37):
```python
    # 1. Idempotency guard — indexed COUNT query (scale-independent, hits idx_memories_run_id)
    if memory.count(MemoryKind.RUN, run_id=run_id) > 0:
        return
```
Gotchas uses signature-based dedup instead of run_id. Before insert, query `get_by_kind(INSIGHT)` and filter by `metadata.signature`. On match → `memory.update(existing)` with incremented count + new last_seen; on miss → `memory.add(new_entry)`.

**MemoryEntry construction with timestamp seam** (journal.py L98-109):
```python
    tags = ["run"] + (["dry_run"] if dry_run else [])
    entry = MemoryEntry(
        id=_new_id(),
        kind=MemoryKind.RUN,
        content=content,
        summary=summary,
        source="journal",
        tags=tags,
        metadata=metadata,
        created_at=ts,
        run_id=run_id,
    )
```
Gotcha entry:
```python
    entry = MemoryEntry(
        id=_new_id(),
        kind=MemoryKind.INSIGHT,
        content=message,
        summary=f"[{source}] {message[:80]}",
        source=source,
        tags=["gotcha", source],
        metadata={
            "signature": sig,
            "source": source,
            "severity": severity,
            "first_seen": ts.isoformat(),
            "last_seen": ts.isoformat(),
            "count": 1,
        },
        created_at=ts,
        run_id=run_id,
    )
```

**`_new_id()` helper** (journal.py L130-134):
```python
def _new_id() -> str:
    """Generate a 12-char hex ID matching MemoryEntry.create() convention."""
    from uuid import uuid4
    return uuid4().hex[:12]
```
Copy verbatim into gotchas.py.

**Mirror file write pattern** (journal.py `_append_runlog` L137-163):
```python
def _append_runlog(root, run_id, ts, steps, artifacts_changed, delta_line, dry_run) -> None:
    """Append a section to .planning/RUNLOG.md. Never raises."""
    try:
        runlog = root / ".planning" / "RUNLOG.md"
        runlog.parent.mkdir(parents=True, exist_ok=True)
        ...
        with runlog.open("a") as fh:
            fh.write(...)
    except Exception:
        pass
```
For GOTCHAS.md the write is a **rewrite** (not append) — `gotchas_md.write_text(...)` wrapped in `try/except Exception: pass`. Rewrite on every capture_gotcha call (upsert + rewrite keeps MD in sync). Also rewrite on prune.

**Signature normalization** — new to this module, no existing analog. Use stdlib only:
```python
import hashlib, re

def _normalize(message: str) -> str:
    """Strip volatile tokens so the same logical failure produces the same signature."""
    s = message.lower()
    s = re.sub(r"/[^\s]+", lambda m: "/" + Path(m.group()).name, s)  # abs paths → basename
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}T[\d:.+Z-]+", "<ts>", s)       # ISO timestamps
    s = re.sub(r"\b[0-9a-f]{12}\b", "<id>", s)                       # 12-hex run_ids
    s = re.sub(r"\b\d+\b", "<n>", s)                                  # digit runs
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _signature(source: str, message: str) -> str:
    raw = source + "|" + _normalize(message)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

**GSD-artifact harvester** — no existing analog for `.planning` markdown parsing in FlowState. Confirm: no YAML/frontmatter parser exists in the codebase (search above showed zero yaml imports in source; `_SEPARATOR = "\n\n---\n\n"` is a string constant, not parsing). Use a minimal line scanner:
```python
def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML-like frontmatter between leading '---' delimiters. No PyYAML."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result
```

---

### `flowstate/memory.py` — add `MemoryStore.update(entry)` (CRUD)

**Analog:** `MemoryStore.add()` (memory.py L153-170)

**`add()` to mirror** (memory.py L153-170):
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

**`update()` follows same structure** — replace INSERT with UPDATE WHERE id = ?; the `memories_au` trigger at L61-66 keeps FTS5 in sync automatically:
```python
    def update(self, entry: MemoryEntry) -> None:
        self._conn.execute(
            """UPDATE memories
               SET kind=?, content=?, summary=?, source=?, tags=?, metadata=?, created_at=?, run_id=?
               WHERE id=?""",
            (
                entry.kind.value,
                entry.content,
                entry.summary,
                entry.source,
                json.dumps(entry.tags),
                json.dumps(entry.metadata),
                entry.created_at.isoformat(),
                entry.run_id,
                entry.id,
            ),
        )
        self._conn.commit()
```

**`memories_au` trigger that fires on UPDATE** (memory.py L61-66):
```sql
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, summary, content, tags)
    VALUES ('delete', old.rowid, old.summary, old.content, old.tags);
    INSERT INTO memories_fts(rowid, summary, content, tags)
    VALUES (new.rowid, new.summary, new.content, new.tags);
END;
```
This fires automatically — no extra FTS sync needed in `update()`.

**`MemoryEntry.create` signature for reference** (memory.py L91-112):
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
            ...
            tags=tags or [],
            metadata=metadata or {},
        )
```
Gotcha entries use `MemoryKind.INSIGHT` with `tags=["gotcha", source]` and `metadata={"signature": ..., "source": ..., "severity": ..., "first_seen": ..., "last_seen": ..., "count": int}`.

---

### `flowstate/context_prefix.py` — add `_read_gotchas_layer` + integrate (transform)

**Analog:** `_read_since_last_run_layer` (context_prefix.py L107-124) — copy this exact structure.

**`_read_since_last_run_layer` to copy** (context_prefix.py L107-124):
```python
def _read_since_last_run_layer(root: Path, memory: Any) -> str:
    """Read last N run-journal entries and format as '## Since Last Run'.

    Returns empty string when the journal is empty (layer omitted silently).
    Never raises.
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
`_read_gotchas_layer` is structurally identical: swap `_load_journal_prefix_n` → `_load_gotchas_max_entries`, `MemoryKind.RUN` → `MemoryKind.INSIGHT` with tag filter, and heading `## Since Last Run` → `## Gotchas`.

**Config-read idiom** (context_prefix.py L69-104) — copy for three new keys:
```python
def _load_budget(root: Path) -> int:
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_BUDGET_TOKENS
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("context_prefix_budget_tokens")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_BUDGET_TOKENS
```
New helpers follow identical pattern:
- `_load_gotchas_max_entries(root)` → key `"gotchas_max_entries"`, default `10`
- `_load_gotchas_budget_tokens(root)` → key `"gotchas_budget_tokens"`, default `1500`
- `_load_gotchas_enabled(root)` → key `"gotchas_enabled"`, default `True` (bool key — use `isinstance(value, bool)` check)

**CR-01 lesson — budget participation is mandatory.** The CR-01 bug was that `since_last_run_layer` was built but NOT included in the pack fit-ladder candidate token estimate, so the prefix could silently exceed budget. The fix is visible at L226-227 and L244-246: `since_last_run_layer` is included in every `_SEPARATOR.join(filter(None, [...]))` candidate. The gotchas layer MUST join every candidate in the same way.

**Pack fit-ladder candidates** (context_prefix.py L226-227, L244-246):
```python
        candidate = _SEPARATOR.join(
            filter(None, [fixtures_layer, pack_raw, memory_layer, since_last_run_layer])
        )
        ...
        candidate2 = _SEPARATOR.join(
            filter(
                None,
                [fixtures_layer, pack_compressed, memory_layer, since_last_run_layer],
            )
        )
```
After inserting `gotchas_layer`, both candidates become:
```python
        candidate = _SEPARATOR.join(
            filter(None, [fixtures_layer, pack_raw, gotchas_layer, memory_layer, since_last_run_layer])
        )
```

**Final budget guard** (context_prefix.py L268-279):
```python
    full_assembly = _SEPARATOR.join(
        filter(None, [fixtures_layer, pack_layer, memory_layer, since_last_run_layer])
    )
    if since_last_run_layer and _estimate_tokens(full_assembly) >= budget:
        con.print(
            "[red]context_prefix: omit since-last-run layer — full prefix exceeds budget "
            f"({budget} tokens); since-last-run dropped (content lives in memory.db)[/red]"
        )
        since_last_run_layer = ""
```
After gotchas layer inserted, extend to also drop gotchas if needed (gotchas before since-last-run in drop order, as it's more stable). Guard structure:
```python
    full_assembly = _SEPARATOR.join(
        filter(None, [fixtures_layer, pack_layer, gotchas_layer, memory_layer, since_last_run_layer])
    )
    if since_last_run_layer and _estimate_tokens(full_assembly) >= budget:
        # drop most dynamic first
        since_last_run_layer = ""
        full_assembly = _SEPARATOR.join(
            filter(None, [fixtures_layer, pack_layer, gotchas_layer, memory_layer])
        )
    if gotchas_layer and _estimate_tokens(full_assembly) >= budget:
        gotchas_layer = ""
```

**Final assembly** (context_prefix.py L282-284):
```python
    layers = [fixtures_layer, pack_layer, memory_layer, since_last_run_layer]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
```
Becomes:
```python
    layers = [fixtures_layer, pack_layer, gotchas_layer, memory_layer, since_last_run_layer]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
```

---

### `flowstate/memory_handlers.py` — extend `on_step_failed` (event-driven)

**Analog:** `on_step_failed` (memory_handlers.py L104-119) — quote in full.

**Existing handler to extend** (memory_handlers.py L104-119):
```python
    @handler("step.failed", priority=EventPriority.AUDIT, profile="minimal")
    def on_step_failed(event: Event) -> None:
        tool_name = event.payload.get("tool", "")
        error = event.payload.get("error", "unknown error")

        store.add(
            MemoryEntry.create(
                MemoryKind.TOOL_RUN,
                f"Tool '{tool_name}' failed: {error}",
                f"{tool_name} failure",
                source=tool_name,
                tags=[tool_name, "failure"],
                run_id=run_id,
            )
        )
```
Add gotcha capture AFTER the existing `store.add(...)`, never before (existing behavior preserved):
```python
        # Also capture as a gotcha — best-effort, never raises
        try:
            from flowstate.gotchas import capture_gotcha
            capture_gotcha(
                store,
                source="executor",
                message=f"Tool '{tool_name}' failed: {error}",
                root=root,
                severity="error",
                run_id=run_id,
            )
        except Exception:
            pass
```
The late import avoids a circular import risk (gotchas.py imports from memory.py; memory_handlers.py imports from memory.py — same layer; but gotchas.py might import doctor.py; keeping it lazy is safe).

**`StepFailed` payload shape** (events/event.py L68-71):
```python
class StepFailed(Event):
    """Emitted when an individual pipeline step fails."""
    event_type: str = "step.failed"
```
Payload keys used: `event.payload.get("tool", "")` and `event.payload.get("error", "unknown error")`.

---

### `flowstate/cli.py` — `gotchas` command (controller, request-response)

**Analog:** `journal` command (cli.py L550-593) — exact clone with different kind + columns.

**Journal command to clone** (cli.py L550-593):
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

Gotchas command adapts this:
- Command name: `"gotchas"`
- Default message on empty: `"[dim]no gotchas recorded yet[/dim]"` → exit 0
- `get_by_kind(MemoryKind.INSIGHT, limit=limit)` then filter `"gotcha" in entry.tags`
- Table columns: Signature (12), Source (12), Severity (10), Count (7), Last Seen (20), Message (min_width=40)
- Sort: already newest-first from `get_by_kind`; for count-desc secondary sort, sort the returned list client-side before display

**`prune` subgroup** — wire as `@gotchas_group.command("prune")` with `--signature` and `--resolved` options. Delete via `store._conn.execute("DELETE FROM memories WHERE id = ?", (entry.id,))` + rewrite GOTCHAS.md. Mirror the `@main.group` / subcommand pattern (cli.py L324-427 for the `memory` group).

**Doctor/repair wiring** (cli.py L664-712 for doctor, L715-769 for repair):
```python
    state = load_state(root)
    findings = run_doctor(state, root)
    ...
    for d in findings:
        ...
```
After `findings` is collected in both `doctor` and `repair`, add gotcha capture for error/warning severity:
```python
    # Capture doctor findings as gotchas — best-effort
    try:
        from flowstate.gotchas import capture_gotcha
        from flowstate.memory import MemoryStore
        with MemoryStore(root=root) as store:
            for d in findings:
                if d.severity in {"error", "warning"}:
                    capture_gotcha(
                        store,
                        source="doctor",
                        message=d.message,
                        root=root,
                        severity=d.severity,
                    )
    except Exception:
        pass
```

---

### `flowstate/journal.py` — populate gotchas metadata slot (service, CRUD)

**Lines to update:**

`metadata["gotchas"] = []` at journal.py L79 → populate with gotcha signatures captured this run. The caller (orchestrator) must pass `gotcha_signatures: list[str]` into `append_run_entry`, or `append_run_entry` queries the store for INSIGHT+gotcha entries with `run_id=run_id` after the main entry is written. The in-band query approach avoids signature threading — query the store for gotchas with matching run_id:
```python
    # Populate gotchas slot from memory (gotchas captured this run)
    try:
        gotcha_entries = memory.get_by_kind(MemoryKind.INSIGHT, limit=100)
        this_run_sigs = [
            e.metadata.get("signature", "")
            for e in gotcha_entries
            if run_id and e.run_id == run_id and "gotcha" in e.tags
        ]
        metadata["gotchas"] = this_run_sigs
    except Exception:
        metadata["gotchas"] = []
```

RUNLOG line at journal.py L158:
```python
            fh.write("- gotchas: (none this phase)\n")
```
→ replace with actual signatures:
```python
            gotchas_str = ", ".join(gotchas) if gotchas else "(none this run)"
            fh.write(f"- gotchas: {gotchas_str}\n")
```
where `gotchas` is extracted from `metadata["gotchas"]`.

---

### `flowstate/orchestrator.py` — harvest at pipeline start (orchestrator)

**Analog:** `append_run_entry` call at orchestrator.py L313-317:
```python
    # Journal: write delta entry after all steps complete
    try:
        append_run_entry(memory, state, run_id, root=root, dry_run=dry_run)
    except Exception as exc:
        console.print(f"  [yellow]journal: non-fatal error: {exc}[/yellow]")
```

Add `harvest_planning_gotchas` at pipeline START (before adapters run) using the same try/except wrapper:
```python
    # Harvest GSD-artifact gotchas from prior phases — best-effort, never raises
    try:
        from flowstate.gotchas import harvest_planning_gotchas
        harvest_planning_gotchas(memory, root)
    except Exception as exc:
        console.print(f"  [yellow]gotchas harvest: non-fatal error: {exc}[/yellow]")
```
Place this immediately after `memory = MemoryStore(root=root)` is opened and before the first adapter step.

---

## Shared Patterns

### Never-raises contract
**Source:** `flowstate/journal.py` L110-113 (inner try/except) + L147-163 (`_append_runlog`)
**Apply to:** `capture_gotcha`, `_rewrite_gotchas_md`, `harvest_planning_gotchas`, `_read_gotchas_layer`, `on_step_failed` gotcha extension, doctor/repair CLI wiring
```python
    try:
        ...
    except Exception:
        pass  # or: return
```
The rule from CONTEXT.md: "make `capture_gotcha` self-contained, not reliant on a caller's wrapper — Phase-6 WR-01." Every function that touches storage or file I/O wraps its own body.

### Config-read idiom
**Source:** `flowstate/context_prefix.py` L69-104 (`_load_budget`, `_load_journal_prefix_n`)
**Apply to:** `_load_gotchas_max_entries`, `_load_gotchas_budget_tokens`, `_load_gotchas_enabled`
```python
def _load_budget(root: Path) -> int:
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_BUDGET_TOKENS
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("context_prefix_budget_tokens")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_BUDGET_TOKENS
```

### MemoryStore open/close pattern for CLI commands
**Source:** `flowstate/cli.py` L566-569 (journal command)
**Apply to:** `gotchas` command, doctor/repair gotcha wiring
```python
    try:
        store = MemoryStore(root=root)
        entries = store.get_by_kind(MemoryKind.RUN, limit=limit)
        store.close()
    except Exception:
        console.print("[dim]no journal entries yet[/dim]")
        return
```

### `_root_was_explicit()` + `resolve_root` pattern
**Source:** `flowstate/cli.py` L30-33 and all command bodies
**Apply to:** `gotchas` command
```python
def _root_was_explicit() -> bool:
    ctx = click.get_current_context()
    return ctx.get_parameter_source("root") == click.core.ParameterSource.COMMANDLINE

root = resolve_root(root, option_was_explicit=_root_was_explicit())
```

---

## No Analog Found

| File/Feature | Role | Reason |
|---|---|---|
| `_parse_frontmatter()` in `gotchas.py` | utility | FlowState has ZERO existing YAML/frontmatter parsing (confirmed: no `yaml` import anywhere in source; `_SEPARATOR = "\n\n---\n\n"` is a plain string constant). Implement as a minimal `--- ... ---` line scanner per CONTEXT.md spec. No PyYAML. |
| `_normalize()` + `_signature()` in `gotchas.py` | utility | No existing normalization or hashing of free-text in the codebase. Use stdlib `hashlib.sha256` + `re`. |
| `harvest_planning_gotchas()` in `gotchas.py` | utility | No `.planning/` markdown artifact parsing exists today — this is genuinely new. Pattern: `Path.glob(".planning/phases/*/*-VERIFICATION.md")` + `_parse_frontmatter()`. |
| `MemoryStore.update()` in `memory.py` | service | No UPDATE path exists today (only INSERT via `add`/`add_many`). Mirror `add()` with UPDATE SQL. The `memories_au` trigger already handles FTS sync. |

---

## Test Patterns

### `tests/test_gotchas.py` (NEW)
**Analog:** `tests/test_journal.py` — use identical fixture/class structure.

**Fixture idiom** (test_journal.py L17-20):
```python
@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s
```

**Never-raises test pattern** (test_journal.py L196-236):
```python
class TestNeverRaises:
    def test_runlog_write_failure_does_not_propagate(
        self, store, state_with_manifest, tmp_path, monkeypatch
    ):
        ...
        # Must not raise
        append_run_entry(store, state_with_manifest, "safe001", root=tmp_path, timestamp=FIXED_TS)
        # Memory entry still landed
        assert store.count(MemoryKind.RUN) == 1

    def test_memory_add_failure_does_not_propagate(self, state_with_manifest, tmp_path, monkeypatch):
        from unittest.mock import MagicMock
        fake_memory = MagicMock(spec=MemoryStore)
        fake_memory.count.return_value = 0
        fake_memory.get_by_kind.return_value = []
        fake_memory.add.side_effect = RuntimeError("simulated storage failure")
        # Must not raise
        append_run_entry(fake_memory, ...)
        fake_memory.add.assert_called_once()
```
Apply identical pattern to `capture_gotcha`.

**Idempotency/dedup test** (test_journal.py L134-140):
```python
class TestIdempotency:
    def test_two_calls_same_run_id_leaves_one_entry(self, store, state_with_manifest, tmp_path):
        append_run_entry(store, ..., "dup001", ...)
        append_run_entry(store, ..., "dup001", ...)
        assert store.count(MemoryKind.RUN) == 1
```
For gotchas: two `capture_gotcha` calls with same message → count=1 entry with `count=2` in metadata.

### `tests/test_context_prefix.py` — gotchas layer tests
**Analog:** `TestSinceLastRunLayer` class (test_context_prefix.py L429-565).

**Layer order test pattern** (test_context_prefix.py L74-95):
```python
class TestLayerOrder:
    def test_fixtures_before_pack_before_memory(self, tmp_path):
        ...
        fixture_idx = result.find("## Eval Fixtures")
        pack_idx = result.find("<pack>body</pack>")
        memory_idx = result.find("## Prior Knowledge")
        assert fixture_idx < pack_idx < memory_idx
```
Add gotchas assertion: `gotchas_idx` between `pack_idx` and `memory_idx`.

**Budget/drop test pattern** (test_context_prefix.py L511-539):
```python
def test_since_last_run_dropped_and_logged_when_over_budget(self, tmp_path):
    ...
    result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50, console=test_console)
    ...
    since_present = "## Since Last Run" in result
    if since_present:
        assert not over_budget
    else:
        assert "since-last-run" in log_output.lower() or "omit" in log_output.lower()
```

### `tests/test_cli.py` — gotchas command tests
**Analog:** `TestJournalCommand` (test_cli.py L592-673).

```python
class TestGotchasCommand:
    def test_gotchas_empty_exits_zero(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "no gotchas recorded yet" in result.output

    def test_gotchas_corrupt_db_exits_zero(self, tmp_path):
        db_path = tmp_path / "memory.db"
        db_path.write_text("not a valid sqlite database")
        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
```

---

## Metadata

**Analog search scope:** `/Users/jhogan/frameworx/flowstate/` (all source modules) + `/Users/jhogan/frameworx/tests/`
**Files read:** journal.py, memory.py, memory_handlers.py, context_prefix.py, doctor.py, repair.py (header), orchestrator.py (L1-50, L300-340), cli.py (L1-45, L550-775), events/event.py (L60-78), tests/test_journal.py, tests/test_context_prefix.py, tests/test_cli.py (L1-50, L589-673)
**Pattern extraction date:** 2026-06-08
