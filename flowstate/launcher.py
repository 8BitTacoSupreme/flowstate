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

# Known tool markers — files/dirs that indicate a tool is installed
TOOL_MARKERS = {
    "gsd": [".planning"],
    "gstack": [".claude/skills/gstack"],
    "superpowers": [".claude/plugins/superpowers"],
}


def detect_tools(root: Path) -> dict[str, bool]:
    """Check what Claude Code extensions are installed/available."""
    results = {}
    home = Path.home()

    for tool, markers in TOOL_MARKERS.items():
        found = False
        for marker in markers:
            # Check project root and home directory
            if (root / marker).exists() or (home / marker).exists():
                found = True
                break
        results[tool] = found

    # GSD skills are loaded if any /gsd:* skills are available
    # Check for .planning dir as proxy (GSD creates it)
    gsd_skills = (root / ".planning").exists()
    results["gsd"] = gsd_skills or results.get("gsd", False)

    return results


def launch_command(
    tool: str, phase: int | None = None, root: Path | None = None
) -> str:
    """Generate the exact claude invocation command for a tool."""
    project_dir = str(root or Path.cwd())

    commands = {
        "gsd": _gsd_command(phase),
        "research": "# Research runs via flowstate init (claude --print)",
        "strategy": "# Strategy runs via flowstate init (claude --print)",
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

    if tools.get("gsd"):
        console.print("  [cyan]flowstate launch gsd 1[/cyan]  — Plan phase 1 with GSD")
    else:
        console.print(
            "  [dim]GSD not detected. Run /gsd:new-project in a Claude Code session.[/dim]"
        )

    # Check what pipeline steps completed
    research_done = state.tools.get("research", state.tools.get("autoresearch"))
    if research_done and research_done.status != ToolStatus.COMPLETED:
        console.print(
            "  [cyan]flowstate init[/cyan]            — Run pipeline (research + strategy)"
        )

    console.print()
