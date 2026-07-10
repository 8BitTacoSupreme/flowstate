"""Session launcher — generates commands for native Claude Code execution.

FlowState prepares context files, then hands off to tools that run natively
inside Claude Code sessions (GSD skills, Gstack commands, etc.).
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowstate.state import FlowStateModel, ToolStatus

console = Console()

# Known tool markers — files/dirs that indicate a tool is installed.
# strategy and discipline are built-in (no external plugin needed).
# GSD is intentionally NOT gated here — FlowState vendors and installs it
# unconditionally (GSD-02/GSD-03), so it is always treated as present.
TOOL_MARKERS = {
    "strategy": [],
    "discipline": [],
}


def detect_tools(root: Path) -> dict[str, bool]:
    """Check what Claude Code extensions are installed/available."""
    # GSD is vendored + installed unconditionally by FlowState (GSD-03); it is
    # always available. No `.planning` marker proxy gates it any longer.
    results: dict[str, bool] = {"gsd": True}
    home = Path.home()

    for tool, markers in TOOL_MARKERS.items():
        if not markers:
            # Built-in tools (strategy, discipline) are always available
            results[tool] = True
            continue
        found = False
        for marker in markers:
            if (root / marker).exists() or (home / marker).exists():
                found = True
                break
        results[tool] = found

    return results


# Vendored-skill handoffs (VEND-04): each surfaces ONLY when its namespace is
# installed under .claude/skills/. Fixed literals — no vendored content is ever
# interpolated into the emitted command (threat T-14-13).
# (launch tool, installed namespace, "cd … && claude → {handoff}" payload).
_SKILL_HANDOFFS: dict[str, tuple[str, str]] = {
    "strategy": ("gstack", "/office-hours"),
    "discipline": ("superpowers", "Use the superpowers test-driven-development skill"),
}


def _skill_installed(root: Path, namespace: str) -> bool:
    """True when a vendored skill namespace is present under .claude/skills/.

    Phase 15 extends the launch surface by adding entries to ``_SKILL_HANDOFFS``;
    this presence check stays the single gate for every vendored handoff.
    """
    return (root / ".claude" / "skills" / namespace).exists()


def _install_prompt(namespace: str) -> str:
    """Guidance shown when a required skill namespace is not yet installed."""
    return f"# {namespace} skills not installed — run: flowstate install-skills"


def launch_command(tool: str, phase: int | None = None, root: Path | None = None) -> str:
    """Generate the exact claude invocation command for a tool."""
    root = root or Path.cwd()
    project_dir = str(root)

    # Skill-gated handoffs: surface only when the vendored namespace is installed.
    if tool in _SKILL_HANDOFFS:
        namespace, handoff = _SKILL_HANDOFFS[tool]
        if not _skill_installed(root, namespace):
            return _install_prompt(namespace)
        return f"cd {project_dir} && claude\n  → {handoff}"

    commands = {
        "gsd": _gsd_command(phase),
        "research": "# Research runs via flowstate init (claude --print)",
    }

    cmd = commands.get(tool)
    if cmd is None:
        return f"# Unknown tool: {tool}"

    return f"cd {project_dir} && claude\n  → {cmd}"


def _gsd_command(phase: int | None = None) -> str:
    """Generate GSD skill command."""
    if phase is not None:
        return f"/gsd:plan-phase {phase}"
    return "/gsd:progress"


def print_next_steps(state: FlowStateModel, root: Path) -> None:
    """Show what to do next based on current state."""
    tools = detect_tools(root)

    console.print()
    console.print(Panel("[bold]Next Steps[/bold]", border_style="blue"))

    # Show context file status
    if state.context_files:
        console.print("\n[bold]Context files created:[/bold]")
        for f in state.context_files:
            path = root / f
            status = "[green]exists[/green]" if path.exists() else "[red]missing[/red]"
            console.print(f"  {f} — {status}")

    # Show tool availability
    console.print("\n[bold]Tool availability:[/bold]")
    tool_table = Table(show_header=False, box=None, padding=(0, 2))
    tool_table.add_column("Tool")
    tool_table.add_column("Status")

    for tool, available in tools.items():
        status = "[green]detected[/green]" if available else "[dim]not found[/dim]"
        tool_table.add_row(tool, status)
    console.print(tool_table)

    # Suggest next action
    console.print("\n[bold]Suggested commands:[/bold]")

    # GSD is always present (vendored + installed by FlowState, GSD-03), so the
    # launch handoff is offered unconditionally — no detect-and-suggest branch.
    console.print("  [cyan]flowstate launch gsd 1[/cyan]  — Plan phase 1 with GSD")

    # Check what pipeline steps completed
    research_done = state.tools.get("research", state.tools.get("autoresearch"))
    if research_done and research_done.status != ToolStatus.COMPLETED:
        console.print(
            "  [cyan]flowstate init[/cyan]            — Run pipeline (research + strategy)"
        )

    console.print()
