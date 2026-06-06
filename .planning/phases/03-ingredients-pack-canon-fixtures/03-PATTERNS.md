# Phase 3: Ingredients — Pack, Canon, Fixtures - Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 8 (5 new/modified source files, 1 new fixture file, 1 interview touch, 1 new test file)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `flowstate/pack.py` | service/utility | request-response (subprocess) | `flowstate/bridge.py` | exact |
| `flowstate/cli.py` (add `pack` cmd) | controller | request-response | `flowstate/cli.py::check_bridge` + `doctor` | exact |
| `flowstate/state.py` (`InstallEntry.kind`) | model | CRUD | `flowstate/state.py::InstallEntry` | exact |
| `flowstate/bridge.py` (CANON + inject_canon) | service | request-response | `flowstate/bridge.py::BridgeConfig` + `run()` | exact |
| `flowstate/context.py` (fixtures + mcp.json + DX-02) | service/utility | file-I/O | `flowstate/context.py::write_context_files` + `_register` | exact |
| `.planning/fixtures/<name>.json` | config | N/A | ECC scenario.json (no codebase analog; use RESEARCH.md shape) | none |
| `flowstate/interview.py` + `state.py::InterviewAnswers` | model | CRUD | existing `InterviewAnswers` + `run_interview()` | exact |
| `tests/test_pack.py` | test | request-response | `tests/test_bridge.py` + `tests/test_cli.py` + `tests/test_doctor.py` | exact |

---

## Pattern Assignments

### `flowstate/pack.py` (service/utility, subprocess)

**Analog:** `flowstate/bridge.py`

**Imports pattern** (`bridge.py` lines 25-33):
```python
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
```

**Locator pattern** (`bridge.py` lines 60-81) — mirror exactly, substituting `FLOWSTATE_REPOMIX_BIN` and `repomix`:
```python
def _find_claude() -> str:
    """Locate the claude CLI binary."""
    # Check explicit env var first
    env_path = os.environ.get("FLOWSTATE_CLAUDE_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("claude")
    if found:
        return found

    # Common install locations
    candidates = [
        Path.home() / ".local" / "bin" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    return ""
```

For `_find_repomix()` substitute:
- Env var: `FLOWSTATE_REPOMIX_BIN`
- `shutil.which("repomix")`
- Candidates: `~/.local/share/pnpm/repomix`, `~/.npm-global/bin/repomix`, `/usr/local/bin/repomix`

**Result dataclass pattern** (`bridge.py` lines 36-42) — copy structure, rename:
```python
@dataclass
class BridgeResult:
    success: bool
    output: str
    exit_code: int = 0
    error: str | None = None
```
New: `PackResult(success, output_path, exit_code, error)` where `output_path: Path | None`.

**Config dataclass pattern** (`bridge.py` lines 44-58):
```python
@dataclass
class BridgeConfig:
    claude_bin: str | None = None
    project_root: Path = field(default_factory=Path.cwd)
    timeout: int = 300
    ...
    def __post_init__(self):
        if self.claude_bin is None:
            self.claude_bin = _find_claude()
```
New: `PackConfig(repomix_bin, project_root, output_path, timeout, compress)` with `__post_init__` calling `_find_repomix()`.

**Graceful-failure pattern** (`bridge.py` lines 120-130):
```python
if not self.available:
    return BridgeResult(
        success=False,
        output="",
        exit_code=1,
        error=(
            "claude CLI not found. Install Claude Code or set "
            "FLOWSTATE_CLAUDE_BIN to the binary path."
        ),
    )
```

**Subprocess invocation pattern** (`bridge.py` lines 168-196):
```python
try:
    result = subprocess.run(
        cmd,
        cwd=self.config.project_root,
        capture_output=True,
        text=True,
        timeout=self.config.timeout,
        env=env,
    )
    return BridgeResult(
        success=result.returncode == 0,
        output=result.stdout,
        exit_code=result.returncode,
        error=result.stderr if result.returncode != 0 else None,
    )
except subprocess.TimeoutExpired:
    return BridgeResult(success=False, output="", exit_code=-1,
                        error=f"claude CLI timed out after {self.config.timeout}s")
except FileNotFoundError:
    return BridgeResult(success=False, output="", exit_code=-1,
                        error=f"claude CLI not found at: {self.config.claude_bin}")
```

**Staleness check** — compare manifest `created_at` against source file mtimes. Pattern: load state, find the pack's `InstallEntry` by path (`.planning/codebase/repomix-pack.xml`), compare `entry.created_at` against `max(p.stat().st_mtime for p in root.rglob("*.py"))`. Return `True` (stale) if any source is newer.

**Public API to expose:**
```python
def run_pack(root: Path, *, compress: bool = False) -> PackResult:
    """Locate repomix, invoke it, return PackResult with output_path."""

def is_pack_stale(root: Path, state: FlowStateModel) -> bool:
    """True if any tracked source file is newer than pack's created_at."""
```

---

### `flowstate/cli.py` — add `pack` command (controller, request-response)

**Analog:** `flowstate/cli.py::check_bridge` (lines 500-524) and `doctor` (lines 526-574)

**Root resolution + import pattern** (`cli.py` lines 500-524):
```python
@main.command("check")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def check_bridge(root: Path | None):
    """Check if the claude CLI bridge is available and configured."""
    from flowstate.bridge import BridgeConfig, ClaudeBridge

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    config = BridgeConfig(project_root=root)
    bridge = ClaudeBridge(config=config)

    if bridge.available:
        console.print(f"[green]claude CLI found:[/green] {config.claude_bin}")
        ...
    else:
        console.print("[red]claude CLI not found.[/red]")
        ...
```

**Non-zero exit pattern** (`cli.py` lines 539-574 in `doctor`):
```python
import sys
...
errors = sum(1 for d in findings if d.severity == "error")
if errors:
    sys.exit(errors)
```

**Rich success/failure output pattern** (`cli.py` lines 516-523):
```python
if bridge.available:
    console.print(f"[green]claude CLI found:[/green] {config.claude_bin}")
    console.print(f"[dim]Timeout: {config.timeout}s | Max turns: {config.max_turns}[/dim]")
else:
    console.print("[red]claude CLI not found.[/red]")
    console.print(
        "[dim]Install Claude Code or set FLOWSTATE_CLAUDE_BIN to the binary path.[/dim]"
    )
```

**New `pack` command shape** — copy `check_bridge` skeleton, add `--force` and `--compress` flags (like `fresh` has `--force`). Call `run_pack(root, compress=compress)`, print `[green]Pack written:[/green] {result.output_path.relative_to(root)}` on success, `sys.exit(1)` on failure.

---

### `flowstate/state.py` — extend `InstallEntry.kind` (model, CRUD)

**Analog:** `flowstate/state.py::InstallEntry` lines 46-54

**Current `kind` Literal** (`state.py` lines 46-54):
```python
class InstallEntry(BaseModel):
    """A single file FlowState owns — recorded at write time, consulted by `fresh`."""

    path: str
    owner: str
    kind: Literal["config", "context", "memory", "research", "artifact"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    checksum: str | None = None
```

**Extend to:**
```python
kind: Literal["config", "context", "memory", "research", "artifact", "pack", "fixture"]
```

**Migration pattern** (`state.py` lines 91-128) — bump version, add migration block for `v0.3.0 → v0.4.0` (no-op for existing entries; Literal extension is backward-compatible since old entries won't have the new values):
```python
# v0.3.0 → v0.4.0 (extend install_manifest kind literals)
if version < "0.4.0":
    data["version"] = "0.4.0"
```

Also update `FlowStateModel.version` default from `"0.3.0"` to `"0.4.0"`.

**Test guard** — `tests/test_install_manifest.py::TestInstallEntry::test_install_entry_accepts_all_valid_kinds` (line 41) must be updated to include `"pack"` and `"fixture"`.

---

### `flowstate/bridge.py` — CANON constant + `BridgeConfig.inject_canon` (service)

**Analog:** `flowstate/bridge.py::BridgeConfig` lines 44-58, `run()` lines 95-104 and 144-145

**Where to add the CANON constant** — at module level after the docstring, before `_SENTINEL`. Source text is `/Users/jhogan/CLAUDE.md` §1–4 verbatim (Think Before Coding / Simplicity First / Surgical Changes / Goal-Driven Execution). Format as a single triple-quoted string constant named `CANON`.

**BridgeConfig extension** (`bridge.py` lines 44-58) — add one field after `effort`:
```python
@dataclass
class BridgeConfig:
    claude_bin: str | None = None
    project_root: Path = field(default_factory=Path.cwd)
    timeout: int = 300
    allowed_tools: list[str] = field(default_factory=list)
    max_turns: int = 10
    model: str | None = None
    max_budget_usd: float | None = None
    effort: str | None = None
    # NEW:
    inject_canon: bool = True
```

**System-prompt prepend pattern** (`bridge.py` lines 144-145) — existing:
```python
if system_prompt:
    cmd.extend(["--system-prompt", system_prompt])
```

Modify to assemble final system prompt before passing to `--system-prompt`:
```python
# Prepend CANON as most-stable CAG layer
if self.config.inject_canon:
    canon_prefix = CANON + "\n\n"
else:
    canon_prefix = ""

final_system = canon_prefix + (system_prompt or "")
if final_system.strip():
    cmd.extend(["--system-prompt", final_system])
```

---

### `flowstate/context.py` — fixtures dir + `.mcp.json` + DX-02 (service, file-I/O)

**Analog:** `flowstate/context.py::write_context_files` lines 171-217 and `_register` lines 23-47

**`_register` helper** (`context.py` lines 23-47) — reuse as-is for all new files:
```python
def _register(
    state: FlowStateModel,
    root: Path,
    path: Path,
    *,
    owner: str,
    kind: str,
) -> None:
    """Add or replace an InstallEntry for the given file on state.install_manifest.

    Idempotent: removes any existing entry for the same relative path before appending.
    """
    rel = str(path.relative_to(root))
    checksum = _sha256_of(path) if kind != "memory" else None
    state.install_manifest = [e for e in state.install_manifest if e.path != rel]
    state.install_manifest.append(
        InstallEntry(
            path=rel,
            owner=owner,
            kind=kind,  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            checksum=checksum,
        )
    )
```

**Dir creation + write + register pattern** (`context.py` lines 177-183):
```python
planning = root / ".planning"
planning.mkdir(exist_ok=True)

project_path = planning / "PROJECT.md"
project_path.write_text(generate_project_md(answers, project_name))
_register(state, root, project_path, owner="context", kind="context")
created.append(project_path)
```

Apply same pattern for:
1. `.planning/fixtures/` dir creation
2. Starter fixture JSON write → `_register(..., kind="fixture")`
3. `.mcp.json` write → `_register(..., kind="config")`

**`generate_claude_md()` DX-02 addition** (`context.py` lines 114-140) — append a repomix guidance section to the returned string:
```python
## Repomix Pack
When analyzing this codebase, consult `.planning/codebase/repomix-pack.xml`
instead of crawling source files each wave. The pack is updated by `flowstate pack`.
```

**New scaffold functions to add in `context.py`:**
```python
def generate_starter_fixture(answers: InterviewAnswers, project_name: str = "") -> dict:
    """Generate a starter ECC-modeled fixture dict from interview answers."""

def scaffold_mcp_json(root: Path) -> dict:
    """Generate .mcp.json content registering repomix-mcp server."""
```

---

### `.planning/fixtures/<name>.json` (config artifact, no code analog)

**No codebase analog.** Use ECC scenario.json shape from REQUIREMENTS.md / CONTEXT.md.

**Required top-level keys:**
```json
{
  "retrieval_questions": ["..."],
  "acceptance_gates": ["..."],
  "forbidden_actions": ["..."],
  "system_contract": "...",
  "few_shot_exemplars": [
    {
      "input": "...",
      "expected_output": "...",
      "rationale": "..."
    }
  ]
}
```

Derived from `InterviewAnswers` fields: `core_problem` → system_contract summary; `milestones` → acceptance_gates seeds; `ten_x_vision` → retrieval_questions seed.

---

### `flowstate/interview.py` + `state.py::InterviewAnswers` (model, CRUD, light touch)

**Analog:** `flowstate/interview.py` lines 60-112, `state.py` lines 28-34

**`InterviewAnswers` model** (`state.py` lines 28-34):
```python
class InterviewAnswers(BaseModel):
    research_focus: str = ""
    core_problem: str = ""
    ten_x_vision: str = ""
    milestones: list[str] = Field(default_factory=list)
    test_coverage: int = 80
    architecture_pattern: str = ""
```
No new fields needed for Phase 3 — fixture content is derived from existing fields at scaffold time. `interview.py` is untouched this phase.

---

### `tests/test_pack.py` (test)

**Analogs:** `tests/test_bridge.py`, `tests/test_cli.py`, `tests/test_doctor.py`

**Monkeypatch subprocess pattern** (`tests/test_bridge.py` lines 46-53 and 64-82):
```python
def test_config_env_override(tmp_path: Path, monkeypatch):
    fake = tmp_path / "claude-custom"
    fake.write_text("#!/bin/sh\necho ok")
    fake.chmod(0o755)

    monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake))
    config = BridgeConfig()
    assert config.claude_bin == str(fake)

def test_run_builds_correct_command(tmp_path: Path):
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho test-output")
    fake_claude.chmod(0o755)
    # ... invoke with fake binary that echoes args
    assert result.success
    assert "test-output" in result.output
```

For `test_pack.py`: create a fake `repomix` shell script that writes a sentinel XML file; monkeypatch `FLOWSTATE_REPOMIX_BIN`; assert `result.output_path` exists.

**CliRunner + `--root` pattern** (`tests/test_cli.py` lines 77-81):
```python
def test_doctor_healthy_install_exits_zero(self, healthy_install):
    runner = CliRunner()
    result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
    assert result.exit_code == 0
    assert "All checks passed" in result.output
```

**`healthy_install` fixture** (`tests/test_cli.py` lines 27-74) — extend or reuse as-is. For pack tests that need a repomix binary, add `fake_repomix` alongside `fake_claude`.

**Env-var monkeypatch pattern** (`tests/test_cli.py` lines 37-41):
```python
fake_claude = tmp_path / "fake_claude"
fake_claude.write_text("#!/bin/sh\nexit 0\n")
fake_claude.chmod(0o755)
monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))
```

**Test classes to write in `tests/test_pack.py`:**
- `TestFindRepomix` — env-var override, PATH detection, missing returns `""`
- `TestRunPack` — success writes `.planning/codebase/repomix-pack.xml`, error returns `PackResult(success=False)`, not-found returns graceful failure
- `TestIsPackStale` — fresh pack not stale, source file newer than pack is stale
- `TestPackCommand` (CliRunner) — `pack --root` exits 0 on success, exits 1 when repomix absent
- `TestCanonInjection` (in `tests/test_bridge.py`) — `inject_canon=True` prepends CANON, `inject_canon=False` omits it

**Import header for `tests/test_pack.py`** (follow `test_bridge.py` header pattern, `test_doctor.py` lines 1-9):
```python
"""Tests for flowstate.pack — repomix locator, run_pack(), staleness check."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from flowstate.pack import PackConfig, PackResult, _find_repomix, is_pack_stale, run_pack
from flowstate.cli import main
```

---

## Shared Patterns

### Manifest Registration
**Source:** `flowstate/context.py::_register` lines 23-47
**Apply to:** `pack.py::run_pack()` (register pack artifact), `context.py` additions (fixture, `.mcp.json`)
```python
_register(state, root, path, owner="pack", kind="pack")
_register(state, root, path, owner="context", kind="fixture")
_register(state, root, path, owner="context", kind="config")
```

### Graceful Binary Absence
**Source:** `flowstate/bridge.py` lines 60-81 (`_find_claude`) + lines 120-130 (`not self.available` guard)
**Apply to:** `flowstate/pack.py::_find_repomix()` + `run_pack()` available check
**Pattern:** Return `""` from locator when not found; check `bool(bin_path)` before invoking subprocess; return result object with `success=False, error="repomix CLI not found..."`.

### Click `--root` Resolution
**Source:** `flowstate/cli.py` lines 30-33, 82-83
**Apply to:** New `pack` Click command
```python
def _root_was_explicit() -> bool:
    ctx = click.get_current_context()
    return ctx.get_parameter_source("root") == click.core.ParameterSource.COMMANDLINE

root = resolve_root(root, option_was_explicit=_root_was_explicit())
```

### Non-zero Exit on Failure
**Source:** `flowstate/cli.py` lines 539-540, 570-574
**Apply to:** `pack` command when `result.success is False`
```python
import sys
...
if not result.success:
    console.print(f"[red]{result.error}[/red]")
    sys.exit(1)
```

### Test Monkeypatch for Subprocess
**Source:** `tests/test_bridge.py` lines 46-52, `tests/test_doctor.py` lines 127-144
**Apply to:** `tests/test_pack.py` — fake repomix binary + `monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake_repomix))`; never shell out to real repomix in tests.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `.planning/fixtures/<name>.json` | config artifact | N/A | No ECC-format fixtures exist in this repo; use REQUIREMENTS.md FIX-01 shape |

---

## Metadata

**Analog search scope:** `flowstate/`, `tests/`
**Files scanned:** 12 source + test files fully read
**Pattern extraction date:** 2026-06-06
