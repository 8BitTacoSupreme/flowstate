"""Base class for tool adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from flowstate.bridge import BridgeConfig, BridgeResult, ClaudeBridge


@dataclass
class ToolResult:
    success: bool
    output: str
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


class ToolAdapter:
    name: str = "base"

    def __init__(self, root: Path, dry_run: bool = False, bridge: ClaudeBridge | None = None):
        self.root = root
        self.dry_run = dry_run
        self._bridge = bridge

    @property
    def bridge(self) -> ClaudeBridge:
        if self._bridge is None:
            config = BridgeConfig(project_root=self.root)
            self._bridge = ClaudeBridge(config=config, dry_run=self.dry_run)
        return self._bridge

    def bridge_to_result(self, br: BridgeResult, artifacts: list[str] | None = None) -> ToolResult:
        return ToolResult(
            success=br.success,
            output=br.output,
            artifacts=artifacts or [],
            error=br.error,
        )

    def run_cmd(self, cmd: list[str], capture: bool = True) -> ToolResult:
        if self.dry_run:
            return ToolResult(
                success=True,
                output=f"[dry-run] Would execute: {' '.join(cmd)}",
            )
        try:
            result = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=capture,
                text=True,
                timeout=300,
            )
            return ToolResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error=f"Command not found: {cmd[0]}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after 300s: {' '.join(cmd)}",
            )
