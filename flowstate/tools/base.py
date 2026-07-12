"""Base class for tool adapters."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from flowstate.bridge import BridgeConfig, BridgeResult, ClaudeBridge
from flowstate.sandbox import wrap

if TYPE_CHECKING:
    from flowstate.memory import MemoryStore


@dataclass
class ToolResult:
    success: bool
    output: str
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


class ToolAdapter:
    name: str = "base"

    def __init__(
        self,
        root: Path,
        dry_run: bool = False,
        bridge: ClaudeBridge | None = None,
        memory: MemoryStore | None = None,
        prior_knowledge: str | None = None,
        sandbox: str = "observe",
    ):
        self.root = root
        self.dry_run = dry_run
        self._bridge = bridge
        self.memory = memory
        # Unified prior_knowledge block built once at orchestrator pipeline start
        # and threaded into every adapter. Default None == "not provided"; adapters
        # coerce with `or ""` at use time. get_memory_context() remains as the
        # escape hatch for callers needing a query-specific slice.
        self.prior_knowledge = prior_knowledge
        # SBX-03/SBX-04: confinement tier for run_cmd's wrap("tool") call.
        self.sandbox = sandbox

    @property
    def bridge(self) -> ClaudeBridge:
        if self._bridge is None:
            # SBX-03: thread the adapter's confinement tier into the lazily-built
            # bridge too, so a caller on this path doesn't silently downgrade to
            # observe when confine was requested (the orchestrator injects an
            # explicit bridge, but this path must not lose the level).
            config = BridgeConfig(project_root=self.root, sandbox=self.sandbox)
            self._bridge = ClaudeBridge(config=config, dry_run=self.dry_run)
        return self._bridge

    def bridge_to_result(self, br: BridgeResult, artifacts: list[str] | None = None) -> ToolResult:
        return ToolResult(
            success=br.success,
            output=br.output,
            artifacts=artifacts or [],
            error=br.error,
        )

    def get_memory_context(self, query: str, max_tokens: int = 1500) -> str:
        """Retrieve relevant prior knowledge for prompt injection."""
        if self.memory is None:
            return ""
        return self.memory.get_context(query, max_tokens=max_tokens)

    def run_cmd(self, cmd: list[str], capture: bool = True) -> ToolResult:
        if self.dry_run:
            return ToolResult(
                success=True,
                output=f"[dry-run] Would execute: {' '.join(cmd)}",
            )
        try:
            cmd, env = wrap(cmd, "tool", self.root, {**os.environ}, tier=self.sandbox)
            result = subprocess.run(
                cmd,
                cwd=self.root,
                capture_output=capture,
                text=True,
                timeout=300,
                env=env,
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
