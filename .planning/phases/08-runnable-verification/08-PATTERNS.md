# Phase 8: Runnable Verification - Pattern Map

**Mapped:** 2026-06-08
**Files analyzed:** 5 (2 new, 2 modified, 1 new test module)
**Analogs found:** 4 / 5 (coverage XML parsing has no codebase analog — stdlib-only new pattern)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `flowstate/verify.py` | service/checker | request-response (pure-Python, no I/O side effects) | `flowstate/doctor.py` | exact — same role, same data flow, same never-raises discipline |
| `flowstate/cli.py` (+`verify` command) | controller/CLI | request-response | `flowstate/cli.py` `doctor` command (L783-845) | exact — clone of doctor's report+exit+capture structure |
| `flowstate/journal.py` (+`append_verify_entry`) | service/writer | event-driven, append-only | `flowstate/journal.py` `append_run_entry` (L18-127) | exact — lightweight sibling of the same function in the same file |
| `tests/test_verify.py` (NEW) | test | N/A | `tests/test_journal.py` + `tests/test_cli.py` | role-match — same CliRunner + MemoryStore + tmp_path idioms |
| `tests/test_journal.py` (+`append_verify_entry` tests) | test | N/A | existing `TestFirstRun` class in `tests/test_journal.py` | exact — extend in same file |

---

## Pattern Assignments

### `flowstate/verify.py` (new, service/checker, pure-Python)

**Analog:** `flowstate/doctor.py`

**Imports pattern** (doctor.py L1-21):
```python
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from flowstate.state import FlowStateModel, ToolStatus

logger = logging.getLogger(__name__)
```

For `verify.py` the imports are narrower — no `hashlib`/`sqlite3`/`os` for the checks themselves, but add `import json`, `import re`, `import xml.etree.ElementTree as ET` (stdlib, new pattern — see "No Analog Found" section below). No `flowstate.bridge` import (LOCKED — pure-Python constraint).

**Result dataclass pattern** (doctor.py L26-31) — mirror exactly, different field names:
```python
@dataclass(frozen=True)
class Diagnosis:
    name: str
    severity: Literal["error", "warning", "info"]
    message: str
    fix_hint: str | None = None
```

`VerifyResult` follows the same shape:
```python
@dataclass(frozen=True)
class VerifyResult:
    gate: str                              # the raw gate string from the fixture
    status: Literal["pass", "fail", "skip"]
    message: str
    fixture: str                           # basename of the fixture file it came from
```

**Checker registry + run_verify pattern** (doctor.py L197-223) — direct structural mirror:
```python
def run_doctor(state: FlowStateModel, root: Path) -> list[Diagnosis]:
    """Run every check; never raises. Returns aggregated diagnoses."""
    import flowstate.doctor as _self  # late binding so monkeypatches take effect

    checks = [
        ("manifest_integrity", lambda: _self.check_manifest_integrity(state, root)),
        ("memory_schema", lambda: _self.check_memory_schema(root)),
        ("root_resolution", lambda: _self.check_root_resolution(root)),
        ("claude_cli", lambda: _self.check_claude_cli()),
        ("stale_status", lambda: _self.check_stale_status(state)),
        ("orphan_files", lambda: _self.check_orphan_files(state, root)),
    ]
    findings: list[Diagnosis] = []
    for name, fn in checks:
        try:
            findings.extend(fn())
        except Exception as e:
            logger.exception("doctor check %s raised", name)
            findings.append(
                Diagnosis(
                    name=f"{name}_failed",
                    severity="error",
                    message=f"Check raised: {e}",
                    fix_hint=None,
                )
            )
    return findings
```

`run_verify(state, root)` mirrors this: iterates `root / ".planning/fixtures/*.json"`, loads each with per-fixture try/except (skip malformed), extracts `acceptance_gates` + `forbidden_actions`, dispatches each gate string through the checker registry (artifact-integrity runs once regardless, coverage gate runs on pattern match, everything else is SKIP). Never raises.

**Artifact-integrity check pattern** (doctor.py L34-66 `check_manifest_integrity`) — reuse the same disk-existence check; simplify to existence + non-empty (no checksum re-verification needed for verify's stated scope):
```python
def check_manifest_integrity(state: FlowStateModel, root: Path) -> list[Diagnosis]:
    """Verify every install_manifest entry exists on disk and checksum matches."""
    findings: list[Diagnosis] = []
    for entry in state.install_manifest:
        path = root / entry.path
        if not path.exists():
            findings.append(
                Diagnosis(
                    name="manifest_integrity",
                    severity="error",
                    message=f"Manifest file missing: {entry.path}",
                    ...
                )
            )
            continue
        if entry.checksum is not None and path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            ...
    return findings
```

For verify: exclude `entry.checksum is None` entries (memory.db). Check `path.exists()` and `path.stat().st_size > 0`. Produce a `VerifyResult(gate="produced-artifact-integrity", status="fail", ...)` per missing/empty artifact.

**Fixture schema consumed by verify** (context.py L185-200) — the exact gate text patterns:
```python
# acceptance_gates — seeded from milestones + coverage target
acceptance_gates: list[str] = []
for milestone in answers.milestones:
    acceptance_gates.append(f"Milestone satisfied: {milestone}")
acceptance_gates.append(f"Test coverage meets or exceeds {answers.test_coverage}% as required.")
if len(acceptance_gates) == 1:
    acceptance_gates.insert(0, "All described functionality works as specified in PROJECT.md.")

# forbidden_actions — sensible defaults
forbidden_actions = [
    "Do not invent requirements not established in PROJECT.md.",
    "Do not modify files outside the stated task scope.",
    "Do not skip or disable tests to reach coverage targets.",
    "Do not introduce new runtime dependencies without explicit approval.",
]
```

The coverage gate regex must match `"Test coverage meets or exceeds {N}% as required."`. Use:
```python
_COVERAGE_RE = re.compile(r"coverage meets or exceeds (\d{1,3})%", re.IGNORECASE)
```
All `forbidden_actions` and all unmatched `acceptance_gates` → `VerifyResult(status="skip", message="not mechanically verifiable")`.

**Fixture loader pattern** (context_prefix.py L248-263 `_read_fixtures_layer`) — mirrors per-fixture loading in verify:
```python
def _read_fixtures_layer(root: Path) -> str:
    fixture_path = root / _FIXTURE_PATH
    if not fixture_path.exists():
        return ""
    try:
        raw = fixture_path.read_text().strip()
        # Validate it's parseable JSON, then re-emit compactly for determinism
        data = json.loads(raw)
        compact = json.dumps(data, indent=2, sort_keys=True)
        return f"## Eval Fixtures\n\n```json\n{compact}\n```"
    except Exception:
        return ""
```

`verify.py` version globs `root / ".planning/fixtures/*.json"` instead of loading one fixed path, applies the same `json.loads` + `try/except` per file. Malformed JSON → skip that fixture with a warning result, never raise.

**_FIXTURE_PATH constant** (context_prefix.py L51):
```python
_FIXTURE_PATH = ".planning/fixtures/starter.json"
```
Verify globs the parent dir: `sorted((root / ".planning" / "fixtures").glob("*.json"))`.

---

### `flowstate/cli.py` — new `verify` @main.command() (controller, request-response)

**Analog:** `flowstate/cli.py` doctor command (L783-845) — copy this block wholesale, substituting verify-specific names.

**Full doctor command to clone** (L783-845):
```python
@main.command("doctor")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def doctor(root: Path | None):
    """Run health checks against the FlowState install.

    Exits non-zero (count of error-severity findings) so it composes
    in CI / pre-commit hooks.
    """
    import sys

    from rich.table import Table

    from flowstate.doctor import run_doctor
    from flowstate.state import load_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())
    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    findings = run_doctor(state, root)

    # Capture error/warning findings as gotchas — best-effort, never raises
    try:
        from flowstate.gotchas import capture_gotcha
        from flowstate.memory import MemoryStore as _MemoryStore

        with _MemoryStore(root=root) as _store:
            for d in findings:
                if d.severity in {"error", "warning"}:
                    capture_gotcha(
                        _store, source="doctor", message=d.message, root=root, severity=d.severity
                    )
    except Exception:
        pass

    if not findings:
        console.print("[green]All checks passed.[/green]")
        return

    table = Table(title="flowstate doctor", border_style="blue")
    table.add_column("Check", style="bold")
    table.add_column("Severity")
    table.add_column("Message")
    sev_style = {"error": "red", "warning": "yellow", "info": "dim"}
    for d in findings:
        style = sev_style.get(d.severity, "white")
        table.add_row(
            d.name,
            f"[{style}]{d.severity}[/{style}]",
            d.message,
        )
    console.print(table)

    errors = sum(1 for d in findings if d.severity == "error")
    warnings = sum(1 for d in findings if d.severity == "warning")
    console.print(f"\n[bold]Summary:[/bold] {errors} error(s), {warnings} warning(s)")
    if errors:
        sys.exit(errors)
```

**Verify command adaptations** (same structure, different names/columns):

1. Replace `run_doctor` → `run_verify` from `flowstate.verify`.
2. Table columns: `"Gate"`, `"Status"`, `"Fixture"`, `"Message"` instead of `"Check"`, `"Severity"`, `"Message"`.
3. `sev_style` equivalent: `status_style = {"pass": "green", "fail": "red", "skip": "dim"}`.
4. Summary line: `f"{fails} fail(s), {passes} pass(es), {skips} skip(s)"`.
5. `sys.exit(fails)` where `fails = sum(1 for r in results if r.status == "fail")`.
6. Before the table: check `not (root / ".planning" / "fixtures").exists()` → print "no fixtures to verify" and return (exit 0).
7. Gotcha capture block (L809-821 pattern): `source="verify"`, only on `r.status == "fail"` results, `message=f"{r.gate}: {r.message}"`.
8. After gotcha block and before/after table: call `journal.append_verify_entry(store, root, results)` inside the same best-effort try block (or a separate one).

**resolve_root + _root_was_explicit()** — already in cli.py; use exactly as doctor does at L803.

---

### `flowstate/journal.py` — new `append_verify_entry` (service/writer, append-only)

**Analog:** `flowstate/journal.py` `append_run_entry` (L18-127) — lightweight sibling.

**Signature to mirror** (journal.py L18-26):
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

`append_verify_entry` signature (no `state`, no `run_id`, no `dry_run`):
```python
def append_verify_entry(
    memory: MemoryStore,
    root: Path,
    results: list[Any],  # list[VerifyResult] — avoid circular import; use Any or TYPE_CHECKING
    *,
    timestamp: datetime | None = None,
) -> None:
```

**Idempotency guard** (journal.py L35-37) — verify runs are NOT idempotent by run_id (there is no run_id). Use timestamp-based dedup only if needed, or skip idempotency entirely (each CLI invocation is a distinct event). CONTEXT.md does not require idempotency for verify entries. Omit the guard.

**MemoryEntry construction** (journal.py L108-124):
```python
# 8. Write memory entry — construct directly to set created_at from timestamp seam
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
try:
    memory.add(entry)
except Exception:
    return  # memory write failed; best-effort — never raise into pipeline
```

For `append_verify_entry`: `tags=["verify"]`, `kind=MemoryKind.RUN`, `source="journal"`, `run_id=""` (no pipeline run_id available), metadata structure per CONTEXT.md:
```python
metadata = {
    "verify": True,
    "gates_passed": <int>,
    "gates_failed": <int>,
    "gates_skipped": <int>,
    "failed_signatures": [r.gate for r in results if r.status == "fail"],
}
```

**RUNLOG append idiom** (journal.py L126-177 `_append_runlog`):
```python
def _append_runlog(root, run_id, ts, steps, artifacts_changed, delta_line, dry_run, gotchas=None):
    """Append a section to .planning/RUNLOG.md. Never raises."""
    try:
        runlog = root / ".planning" / "RUNLOG.md"
        runlog.parent.mkdir(parents=True, exist_ok=True)
        ...
        with runlog.open("a") as fh:
            fh.write(f"\n## {ts_iso} — run {run_id}\n")
            fh.write(f"- steps: {steps_str}\n")
            ...
    except Exception:
        pass  # journal failure must never break the pipeline
```

`append_verify_entry` calls its own private `_append_verify_runlog(root, ts, results)` using the same pattern. RUNLOG line format: `## {ts_iso} — verify` with `- gates: {passed} pass / {failed} fail / {skipped} skip\n`.

**Never-raises discipline** — every write path wrapped in `try/except Exception: return` or `pass`, matching journal.py L121-124 and L176-177.

**_new_id() helper** — already defined in journal.py at L141-145; call it directly (same module), no need to duplicate.

---

### `tests/test_verify.py` (new test module)

**Analog:** `tests/test_journal.py` (MemoryStore fixture, state_with_manifest, tmp_path idioms) and `tests/test_cli.py` (CliRunner, exit-code asserts, `healthy_install` fixture).

**Store fixture** (test_journal.py L17-20):
```python
@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s
```

**state_with_manifest fixture** (test_journal.py L23-52):
```python
@pytest.fixture()
def state_with_manifest() -> FlowStateModel:
    """FlowStateModel with a seeded install_manifest for diff testing."""
    state = FlowStateModel()
    state.install_manifest = [
        InstallEntry(
            path="research/report.md",
            owner="research",
            kind="research",
            created_at=datetime.now(UTC),
            checksum="aabbcc112233",
        ),
        InstallEntry(
            path=".planning/ROADMAP.md",
            owner="gsd",
            kind="artifact",
            created_at=datetime.now(UTC),
            checksum="ddeeff445566",
        ),
        InstallEntry(
            path="memory.db",
            owner="memory",
            kind="memory",
            created_at=datetime.now(UTC),
            checksum=None,  # excluded from snapshot
        ),
    ]
    ...
    return state
```

For `tests/test_verify.py`: build `tmp_path / ".planning" / "fixtures" / "starter.json"` from `generate_starter_fixture()` output (context.py) to produce realistic fixtures. Create `tmp_path / ".planning" / "PROJECT.md"` to satisfy the artifact-integrity check.

**CliRunner + exit-code assertion** (test_cli.py L78-82):
```python
def test_doctor_healthy_install_exits_zero(self, healthy_install):
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
    assert result.exit_code == 0
    assert "All checks passed" in result.output
```

`test_verify.py` CLI cases follow this exactly: `runner.invoke(main, ["verify", "--root", str(tmp_path)])`.

**healthy_install fixture pattern** (test_cli.py L26-74) — reuse or adapt for verify tests that exercise the full CLI path:
```python
@pytest.fixture()
def healthy_install(tmp_path, monkeypatch):
    from flowstate.memory import MemoryStore
    from flowstate.state import FlowStateModel, InstallEntry, save_state

    fake_claude = tmp_path / "fake_claude"
    fake_claude.write_text("#!/bin/sh\nexit 0\n")
    fake_claude.chmod(0o755)
    monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))

    with MemoryStore(root=tmp_path):
        pass

    planning = tmp_path / ".planning"
    planning.mkdir()
    pm = planning / "PROJECT.md"
    pm.write_text("# Project\n")
    checksum = hashlib.sha256(pm.read_bytes()).hexdigest()

    state = FlowStateModel()
    state.install_manifest.append(
        InstallEntry(path=".planning/PROJECT.md", owner="context", kind="context",
                     created_at=datetime.now(UTC), checksum=checksum)
    )
    state.install_manifest.append(
        InstallEntry(path="memory.db", owner="memory", kind="memory",
                     created_at=datetime.now(UTC), checksum=None)
    )
    save_state(state, tmp_path)
    return tmp_path
```

---

## Shared Patterns

### Never-Raises Discipline (Phase-6 WR-01)
**Source:** `flowstate/journal.py` L121-124 and L174-177; `flowstate/gotchas.py` L155-156
**Apply to:** `run_verify`, per-fixture loader in verify.py, coverage parser in verify.py, `append_verify_entry`, entire CLI `verify` command's gotcha+journal block.

```python
try:
    memory.add(entry)
except Exception:
    return  # memory write failed; best-effort — never raise into pipeline
```

```python
except Exception:
    pass  # journal failure must never break the pipeline
```

### Exit-Code = Count-of-Failures
**Source:** `flowstate/cli.py` L841-845
**Apply to:** `verify` command

```python
errors = sum(1 for d in findings if d.severity == "error")
...
if errors:
    sys.exit(errors)
```

Verify equivalent: `fails = sum(1 for r in results if r.status == "fail")` → `sys.exit(fails)`.

### Best-Effort Gotcha Capture Block
**Source:** `flowstate/cli.py` L809-821
**Apply to:** `verify` command (source="verify")

```python
# Capture error/warning findings as gotchas — best-effort, never raises
try:
    from flowstate.gotchas import capture_gotcha
    from flowstate.memory import MemoryStore as _MemoryStore

    with _MemoryStore(root=root) as _store:
        for d in findings:
            if d.severity in {"error", "warning"}:
                capture_gotcha(
                    _store, source="doctor", message=d.message, root=root, severity=d.severity
                )
except Exception:
    pass
```

In `verify`: open the same `_MemoryStore(root=root)` context once, capture gotchas for `r.status == "fail"` results, AND call `append_verify_entry(store, root, results)` within the same block.

### MemoryEntry.create / MemoryKind.RUN + Tagged Entry
**Source:** `flowstate/journal.py` L108-124; `flowstate/memory.py` (MemoryEntry, MemoryKind)
**Apply to:** `append_verify_entry`

Tags: `["verify"]`. Kind: `MemoryKind.RUN`. Source: `"journal"`. The `## Since Last Run` prefix layer in `context_prefix.py` calls `memory.get_by_kind(MemoryKind.RUN, limit=n)` — verify entries are surfaced automatically with no layer changes needed.

### capture_gotcha Signature
**Source:** `flowstate/gotchas.py` L94-103
**Apply to:** `verify` command and indirectly `append_verify_entry`

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

Call site in `verify` command: `capture_gotcha(_store, source="verify", message=f"{r.gate}: {r.message}", root=root, severity="error")`.

### `from __future__ import annotations` Header
**Source:** Every module in `flowstate/` (doctor.py L8, journal.py L8, gotchas.py etc.)
**Apply to:** `verify.py`, any new test file.

---

## No Analog Found

| File / Pattern | Role | Reason |
|---|---|---|
| `xml.etree.ElementTree` coverage.xml parsing in `verify.py` | utility (coverage checker) | No XML parsing exists anywhere in `flowstate/`. This is a new pattern. Use stdlib `xml.etree.ElementTree`: `tree = ET.parse(str(coverage_xml)); root_el = tree.getroot(); line_rate = float(root_el.get("line-rate", "0"))`. Wrap in `try/except Exception` — malformed/absent XML → SKIP. Never shell out to `coverage report`. |

**Guidance for coverage XML parsing (no codebase analog — use stdlib directly):**
```python
import xml.etree.ElementTree as ET

def _parse_coverage_xml(root: Path) -> float | None:
    """Return line-rate (0.0–1.0) from coverage.xml, or None if absent/malformed."""
    cov_xml = root / "coverage.xml"
    if not cov_xml.exists():
        return None
    try:
        tree = ET.parse(str(cov_xml))
        rate = tree.getroot().get("line-rate")
        if rate is None:
            return None
        return float(rate)
    except Exception:
        return None
```

If `_parse_coverage_xml` returns `None` and `.coverage` also absent → `VerifyResult(status="skip", message="no coverage report found")`. Never shell out; `.coverage` binary/SQLite file is not parseable without the `coverage` package (banned — no new deps).

---

## Metadata

**Analog search scope:** `flowstate/`, `tests/`
**Files read:** doctor.py, journal.py, gotchas.py, context_prefix.py, context.py (L144-223), state.py (L44-83), cli.py (L783-845), tests/test_cli.py (L1-165), tests/test_journal.py (L1-70)
**Pattern extraction date:** 2026-06-08
