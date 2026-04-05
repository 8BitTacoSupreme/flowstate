"""Base class for tool adapters."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolResult:
    success: bool
    output: str
    artifacts: list[str]
    error: str | None = None


class ToolAdapter:
    name: str = "base"

    def __init__(self, root: Path, dry_run: bool = False):
        self.root = root
        self.dry_run = dry_run

    def run_cmd(self, cmd: list[str], capture: bool = True) -> ToolResult:
        if self.dry_run:
            return ToolResult(
                success=True,
                output=f"[dry-run] Would execute: {' '.join(cmd)}",
                artifacts=[],
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
                artifacts=[],
                error=result.stderr if result.returncode != 0 else None,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                artifacts=[],
                error=f"Command not found: {cmd[0]}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                artifacts=[],
                error=f"Command timed out after 300s: {' '.join(cmd)}",
            )
