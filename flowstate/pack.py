"""Repomix pack service — locate the repomix CLI, produce the codebase pack, detect staleness.

Mirrors flowstate/bridge.py structure: locator function + result/config dataclasses +
public run_pack() / is_pack_stale() functions.

The pack artifact lives at .planning/codebase/repomix-pack.xml and is registered on
install_manifest with kind="pack" so flowstate fresh / doctor can track it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


def _find_repomix() -> str:
    """Locate the repomix CLI binary.

    Resolution order:
    1. FLOWSTATE_REPOMIX_BIN env var (must point to an existing file)
    2. shutil.which("repomix") (PATH search)
    3. Common install locations for Node global packages
    """
    env_path = os.environ.get("FLOWSTATE_REPOMIX_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("repomix")
    if found:
        return found

    # Common install locations for Node global packages
    candidates = [
        Path.home() / ".local" / "share" / "pnpm" / "repomix",
        Path.home() / ".npm-global" / "bin" / "repomix",
        Path("/usr/local/bin/repomix"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    return ""


@dataclass
class PackResult:
    """Result of a run_pack() invocation."""

    success: bool
    output_path: Path | None = None
    exit_code: int = 0
    error: str | None = None


@dataclass
class PackConfig:
    """Configuration for a repomix pack invocation."""

    repomix_bin: str | None = None
    project_root: Path = field(default_factory=Path.cwd)
    output_path: Path | None = None
    timeout: int = 300
    compress: bool = False

    def __post_init__(self):
        if self.repomix_bin is None:
            self.repomix_bin = _find_repomix()
        if self.output_path is None:
            self.output_path = self.project_root / ".planning" / "codebase" / "repomix-pack.xml"


def run_pack(root: Path, *, compress: bool = False) -> PackResult:
    """Locate repomix, invoke it, register the pack artifact, and return PackResult.

    Args:
        root: Project root directory. The pack is written to
              <root>/.planning/codebase/repomix-pack.xml.
        compress: Pass --compress to repomix (reduces token count in the pack).

    Returns:
        PackResult with success=True and output_path set on success, or
        success=False with a human-readable error message when repomix is absent
        or exits non-zero.
    """
    config = PackConfig(project_root=root, compress=compress)

    if not config.repomix_bin:
        return PackResult(
            success=False,
            exit_code=1,
            error=(
                "repomix CLI not found. Install repomix or set "
                "FLOWSTATE_REPOMIX_BIN to the binary path."
            ),
        )

    # Ensure output directory exists
    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        config.repomix_bin,
        "--output",
        str(config.output_path),
        "--style",
        "xml",
    ]
    if compress:
        cmd.append("--compress")
    cmd.append(str(root))

    try:
        result = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=config.timeout,
        )
        if result.returncode != 0:
            return PackResult(
                success=False,
                exit_code=result.returncode,
                error=result.stderr or f"repomix exited with code {result.returncode}",
            )
    except subprocess.TimeoutExpired:
        return PackResult(
            success=False,
            exit_code=-1,
            error=f"repomix timed out after {config.timeout}s",
        )
    except FileNotFoundError:
        return PackResult(
            success=False,
            exit_code=-1,
            error=f"repomix not found at: {config.repomix_bin}",
        )

    # Register the pack artifact on install_manifest
    from flowstate.context import _register
    from flowstate.state import load_state, save_state

    state = load_state(root)
    _register(state, root, config.output_path, owner="pack", kind="pack")
    save_state(state, root)

    return PackResult(success=True, output_path=config.output_path, exit_code=0)


def is_pack_stale(root: Path, state) -> bool:
    """Return True if the pack artifact is absent or any *.py source is newer than it.

    Args:
        root: Project root directory.
        state: FlowStateModel — consulted for the pack's install_manifest entry.

    Returns:
        True  — pack needs regeneration (no entry, or a source file is newer).
        False — pack is current (all sources older than pack's created_at).
    """
    rel = ".planning/codebase/repomix-pack.xml"
    entry = next((e for e in state.install_manifest if e.path == rel), None)
    if entry is None:
        return True

    py_files = list(root.rglob("*.py"))
    if not py_files:
        return False

    newest_source_mtime = max(p.stat().st_mtime for p in py_files)
    return newest_source_mtime > entry.created_at.timestamp()
