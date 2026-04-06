"""ClaudeBridge — invokes the `claude` CLI in non-interactive mode.

This is the core integration layer between FlowState and the Claude Code
runtime. All four GrandSlam tools route through here for real execution.

Claude CLI usage:
    claude --print [options] "prompt text"

The prompt is a positional argument, not a flag.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_SENTINEL = object()


@dataclass
class BridgeResult:
    success: bool
    output: str
    exit_code: int = 0
    error: str | None = None


@dataclass
class BridgeConfig:
    claude_bin: str | None = None
    project_root: Path = field(default_factory=Path.cwd)
    timeout: int = 300
    allowed_tools: list[str] = field(default_factory=list)
    max_turns: int = 10

    def __post_init__(self):
        if self.claude_bin is None:
            self.claude_bin = _find_claude()


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


class ClaudeBridge:
    """Executes prompts through the claude CLI in non-interactive (print) mode."""

    def __init__(self, config: BridgeConfig | None = None, dry_run: bool = False):
        self.config = config or BridgeConfig()
        self.dry_run = dry_run

    @property
    def available(self) -> bool:
        return bool(self.config.claude_bin)

    def run(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        output_format: str = "text",
        max_turns: int | None = None,
    ) -> BridgeResult:
        """Execute a prompt through claude CLI.

        Args:
            prompt: The prompt text (positional arg to claude CLI).
            system_prompt: Optional system prompt override.
            allowed_tools: Tool permissions (e.g., ["Read", "Bash(git:*)"]).
            output_format: "text" or "json".
            max_turns: Max agentic turns for this invocation.
        """
        if self.dry_run:
            return BridgeResult(
                success=True,
                output=f"[dry-run] claude prompt ({len(prompt)} chars): {prompt[:120]}...",
            )

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

        cmd = [self.config.claude_bin, "--print"]

        if output_format == "json":
            cmd.extend(["--output-format", "json"])

        turns = max_turns or self.config.max_turns
        cmd.extend(["--max-turns", str(turns)])

        tools = allowed_tools or self.config.allowed_tools
        if tools:
            cmd.extend(["--allowedTools", ",".join(tools)])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        # "--" separates CLI flags from the positional prompt.
        # Without this, flags inside the prompt (e.g., "/gsd:new-project --auto")
        # get parsed as claude CLI flags instead of prompt content.
        cmd.append("--")
        cmd.append(prompt)

        # Unset CLAUDECODE env var to allow nested invocation
        env = {**os.environ}
        env.pop("CLAUDECODE", None)

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
            return BridgeResult(
                success=False,
                output="",
                exit_code=-1,
                error=f"claude CLI timed out after {self.config.timeout}s",
            )
        except FileNotFoundError:
            return BridgeResult(
                success=False,
                output="",
                exit_code=-1,
                error=f"claude CLI not found at: {self.config.claude_bin}",
            )

    def invoke_skill(self, skill: str, args: str = "") -> BridgeResult:
        """Invoke a Claude Code skill (e.g., 'gsd:new-project').

        Skills are slash commands that get expanded into full prompts
        within the claude session.
        """
        prompt = f"/{skill}"
        if args:
            prompt += f" {args}"

        return self.run(
            prompt,
            allowed_tools=[
                "Read",
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
            ],
            max_turns=15,
        )
