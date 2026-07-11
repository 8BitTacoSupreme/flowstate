"""ClaudeBridge — invokes the `claude` CLI in non-interactive mode.

This is the core integration layer between FlowState and the Claude Code
runtime. All four GrandSlam tools route through here for real execution.

Claude CLI usage:
    claude --print [options] "prompt text"

The prompt is a positional argument, not a flag.

Prompt cache behavior:
    Anthropic's server-side prompt cache fires automatically for back-to-back
    `claude --print` subprocesses with matching ≥1024-token prefixes; no
    per-call CLI flag exists or is needed. Empirically confirmed in spike
    260525-o6h (see .planning/quick/260525-o6h-spike-confirm-claude-print-
    server-side-p/260525-o6h-SPIKE.md) via `usage.cache_read_input_tokens`
    in `--output-format json` responses. Default TTL is 5 minutes; set
    `BridgeConfig.enable_prompt_caching_1h = True` to raise it to 1 hour
    for eligible API-key accounts (injects ENABLE_PROMPT_CACHING_1H=1 env).
    FlowState's layered CAG prefix (Phase 4, build_context_prefix()) produces
    a byte-identical user-prompt prefix across pipeline steps — see the
    ClaudeBridge class docstring for the full most-stable-first layer ordering.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

CANON = """\
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.\
"""

_SENTINEL = object()


@dataclass(frozen=True)
class BridgeUsage:
    """Real per-call token consumption from `claude --print --output-format json`.

    Populated from the response `usage` sub-object; missing keys default to 0.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0


@dataclass
class BridgeResult:
    success: bool
    output: str
    exit_code: int = 0
    error: str | None = None
    # Appended after existing fields to preserve positional construction.
    usage: BridgeUsage | None = None
    duration_s: float | None = None


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
    inject_canon: bool = True
    enable_prompt_caching_1h: bool = False

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
    """Executes prompts through the claude CLI in non-interactive (print) mode.

    Prompt cache — most-stable-first layer ordering
    ───────────────────────────────────────────────
    Anthropic's server-side prompt cache fires for back-to-back subprocesses that
    share a ≥1024-token prefix. FlowState assembles the full CAG stack in this order
    (most-stable-first) so that as many layers as possible cache across pipeline steps:

      1. System prompt — CANON (Phase 3, ``inject_canon=True``). Most stable; changes
         only when the user updates their CLAUDE.md. Outer-most layer, first to cache.
      2. User prompt prefix (Phase 4, assembled by ``build_context_prefix()``):
           a. Fixtures — ``.planning/fixtures/starter.json``. Static within a run.
           b. Pack    — ``.planning/codebase/repomix-pack.xml``. Semi-stable.
           c. Memory  — FTS5 search results. Most dynamic; placed last.
      3. Step prompt — per-adapter research/strategy/GSD instructions. Most volatile.

    The byte-identical prefix produced by ``build_context_prefix()`` across the three
    Research → Strategy → GSD calls is what makes the implicit server-side cache hit
    (confirmed in spike 260525-o6h: -32% wall time, -37% API cost on call 2).

    Opt-in 1-hour cache TTL
    ───────────────────────
    Set ``BridgeConfig.enable_prompt_caching_1h = True`` to inject
    ``ENABLE_PROMPT_CACHING_1H=1`` into the subprocess environment. This raises the
    cache TTL from 5 minutes to 1 hour for API-key accounts that have the feature
    enabled. Default is ``False`` (standard 5-min TTL, no env change).
    """

    def __init__(self, config: BridgeConfig | None = None, dry_run: bool = False):
        self.config = config or BridgeConfig()
        self.dry_run = dry_run
        # Cumulative per-run consumption across all run() calls on this instance.
        # Plan 02 reads these off the shared pipeline bridge; not persisted here.
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_cache_read: int = 0
        self.total_wall_clock_s: float = 0.0

    @property
    def available(self) -> bool:
        return bool(self.config.claude_bin)

    def _accumulate(self, result: BridgeResult) -> None:
        """Fold a non-dry, non-error result into the instance totals."""
        if not result.success:
            # Error/timeout returns measure no real work.
            return
        if result.duration_s is not None:
            self.total_wall_clock_s += result.duration_s
        if result.usage is not None:
            self.total_tokens_in += result.usage.tokens_in
            self.total_tokens_out += result.usage.tokens_out
            self.total_cache_read += result.usage.cache_read

    def run(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        allowed_tools: list[str] | None = None,
        output_format: str = "text",
        max_turns: int | None = None,
        model: str | None = _SENTINEL,
    ) -> BridgeResult:
        """Execute a prompt through claude CLI.

        Args:
            prompt: The prompt text (positional arg to claude CLI).
            system_prompt: Optional system prompt override.
            allowed_tools: Tool permissions (e.g., ["Read", "Bash(git:*)"]).
            output_format: "text" or "json".
            max_turns: Max agentic turns for this invocation.
            model: Model override for this call. _SENTINEL = use config default.
        """
        if self.dry_run:
            # Dry runs measure no real LLM work: usage/duration_s stay None.
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

        # Prepend CANON as most-stable CAG layer
        canon_prefix = CANON + "\n\n" if self.config.inject_canon else ""
        final_system = canon_prefix + (system_prompt or "")
        if final_system.strip():
            cmd.extend(["--system-prompt", final_system])

        # Model: per-call override > config default
        effective_model = model if model is not _SENTINEL else self.config.model
        if effective_model:
            cmd.extend(["--model", effective_model])

        if self.config.max_budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(self.config.max_budget_usd)])

        if self.config.effort:
            cmd.extend(["--effort", self.config.effort])

        # "--" separates CLI flags from the positional prompt.
        # Without this, flags inside the prompt (e.g., "/gsd:new-project --auto")
        # get parsed as claude CLI flags instead of prompt content.
        cmd.append("--")
        cmd.append(prompt)

        # Unset CLAUDECODE env var to allow nested invocation
        env = {**os.environ}
        env.pop("CLAUDECODE", None)
        # Opt-in: raise cache TTL from 5 min to 1 h for eligible API-key accounts
        if self.config.enable_prompt_caching_1h:
            env["ENABLE_PROMPT_CACHING_1H"] = "1"

        try:
            start = time.monotonic()
            result = subprocess.run(
                cmd,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=env,
            )
            duration_s = time.monotonic() - start

            output = result.stdout
            usage: BridgeUsage | None = None
            if output_format == "json":
                # Never raise: malformed/absent `result` → usage=None, keep raw stdout.
                try:
                    parsed = json.loads(result.stdout)
                    if isinstance(parsed, dict) and "result" in parsed:
                        output = parsed["result"]
                        raw_usage = parsed.get("usage") or {}
                        usage = BridgeUsage(
                            tokens_in=raw_usage.get("input_tokens", 0),
                            tokens_out=raw_usage.get("output_tokens", 0),
                            cache_read=raw_usage.get("cache_read_input_tokens", 0),
                        )
                except (json.JSONDecodeError, ValueError, TypeError):
                    output = result.stdout
                    usage = None

            bridge_result = BridgeResult(
                success=result.returncode == 0,
                output=output,
                exit_code=result.returncode,
                error=result.stderr if result.returncode != 0 else None,
                usage=usage,
                duration_s=duration_s,
            )
            self._accumulate(bridge_result)
            return bridge_result
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
