"""FlowState CLI — entrypoint for the context orchestrator."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from flowstate import __version__

console = Console()

BANNER = r"""
  _____ _              ____  _        _
 |  ___| | _____      / ___|| |_ __ _| |_ ___
 | |_  | |/ _ \ \ /\ / /\___ \| __/ _` | __/ _ \
 |  _| | | (_) \ V  V /  ___) | || (_| | ||  __/
 |_|   |_|\___/ \_/\_/  |____/ \__\__,_|\__\___|
"""


@click.group()
@click.version_option(__version__, prog_name="flowstate")
def main():
    """FlowState — The Context Orchestrator."""


@main.command()
@click.option("--dry-run", is_flag=True, help="Simulate tool execution without calling real CLIs.")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
@click.option("--skip-interview", is_flag=True, help="Skip the interview and use existing state.")
@click.option(
    "--model",
    type=str,
    default=None,
    help="Claude model to use (e.g., sonnet, opus, haiku).",
)
@click.option(
    "--budget",
    type=float,
    default=None,
    help="Max spend per bridge call in USD (e.g., 0.50).",
)
@click.option(
    "--effort",
    type=str,
    default=None,
    help="Effort level for claude CLI (e.g., low, medium, high).",
)
def init(
    dry_run: bool,
    root: Path,
    skip_interview: bool,
    model: str | None,
    budget: float | None,
    effort: str | None,
):
    """Initialize a new FlowState project through the pipeline."""
    from flowstate.interview import run_interview
    from flowstate.orchestrator import run_pipeline
    from flowstate.state import load_state, save_state

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    state.preferences.dry_run = dry_run
    if model:
        state.preferences.model = model
    if budget is not None:
        state.preferences.max_budget_usd = budget
    if effort:
        state.preferences.effort = effort

    if not skip_interview:
        run_interview(state)
        save_state(state, root)

    run_pipeline(state, root)
    save_state(state, root)


@main.command()
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def status(root: Path):
    """Show the current state of the FlowState pipeline."""
    from flowstate.orchestrator import print_status

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    print_status(root)


@main.command()
@click.argument("phase", type=int)
@click.option("--dry-run", is_flag=True, help="Simulate execution.")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
@click.option(
    "--model",
    type=str,
    default=None,
    help="Claude model to use (e.g., sonnet, opus, haiku).",
)
@click.option(
    "--budget",
    type=float,
    default=None,
    help="Max spend per bridge call in USD (e.g., 0.50).",
)
@click.option(
    "--effort",
    type=str,
    default=None,
    help="Effort level for claude CLI (e.g., low, medium, high).",
)
def run(
    phase: int,
    dry_run: bool,
    root: Path,
    model: str | None,
    budget: float | None,
    effort: str | None,
):
    """Run a specific GSD phase (prints native session command)."""
    from flowstate.orchestrator import run_phase
    from flowstate.state import load_state, save_state

    state = load_state(root)
    state.preferences.dry_run = dry_run
    if model:
        state.preferences.model = model
    if budget is not None:
        state.preferences.max_budget_usd = budget
    if effort:
        state.preferences.effort = effort

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    run_phase(state, root, phase)
    save_state(state, root)


@main.command("launch")
@click.argument("tool", type=click.Choice(["gsd", "research", "strategy"]))
@click.argument("phase", type=int, required=False)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def launch(tool: str, phase: int | None, root: Path):
    """Print the native Claude Code command for a tool.

    Examples:
        flowstate launch gsd 1      — Print /gsd:plan-phase 1 command
        flowstate launch gsd        — Print /gsd:progress command
    """
    from flowstate.launcher import launch_command

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    cmd = launch_command(tool, phase, root)
    console.print("\n[bold]Launch command:[/bold]\n")
    console.print(f"  [cyan]{cmd}[/cyan]")
    console.print()


@main.command("context")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def context(root: Path):
    """Regenerate context files from current state."""
    from flowstate.context import write_context_files
    from flowstate.state import load_state, save_state

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    created = write_context_files(state, root)
    save_state(state, root)

    console.print(f"\n[green]{len(created)} context files written:[/green]")
    for p in created:
        console.print(f"  {p.relative_to(root)}")
    console.print()


@main.group()
def memory():
    """Manage the persistent memory store."""


@memory.command("search")
@click.argument("query")
@click.option(
    "--kind",
    type=click.Choice(["research", "strategy", "decision", "tool_run", "insight"]),
    default=None,
    help="Filter by memory kind.",
)
@click.option("--limit", type=int, default=10, help="Max results to return.")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def memory_search(query: str, kind: str | None, limit: int, root: Path):
    """Search stored memories via full-text search."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    store = MemoryStore(root=root)
    kind_filter = MemoryKind(kind) if kind else None
    results = store.search(query, kind=kind_filter, limit=limit)
    store.close()

    if not results:
        console.print(f"[dim]No memories matching '{query}'[/dim]")
        return

    table = Table(title=f"Memory Search: {query}", border_style="blue")
    table.add_column("ID", style="dim", width=12)
    table.add_column("Kind", width=10)
    table.add_column("Summary", min_width=30)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Source", style="dim", width=20)

    for sr in results:
        table.add_row(
            sr.entry.id,
            sr.entry.kind.value,
            sr.entry.summary,
            f"{sr.score:.2f}",
            sr.entry.source or "---",
        )

    console.print(table)


@memory.command("stats")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def memory_stats(root: Path):
    """Show memory counts by kind."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    store = MemoryStore(root=root)

    table = Table(title="Memory Stats", border_style="blue")
    table.add_column("Kind", style="bold")
    table.add_column("Count", justify="right")

    total = 0
    for kind in MemoryKind:
        count = store.count(kind)
        total += count
        table.add_row(kind.value, str(count))
    table.add_row("[bold]total[/bold]", f"[bold]{total}[/bold]")

    store.close()
    console.print(table)


@memory.command("clear")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def memory_clear(root: Path, yes: bool):
    """Delete all stored memories."""
    from flowstate.memory import MemoryStore

    if not yes and not click.confirm("Delete all memories? This cannot be undone"):
        console.print("[dim]Cancelled.[/dim]")
        return

    store = MemoryStore(root=root)
    deleted = store.clear()
    store.close()
    console.print(f"[green]Cleared {deleted} memories.[/green]")


main.add_command(memory)


@main.command("check")
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
def check_bridge(root: Path):
    """Check if the claude CLI bridge is available and configured."""
    from flowstate.bridge import BridgeConfig, ClaudeBridge

    config = BridgeConfig(project_root=root)
    bridge = ClaudeBridge(config=config)

    if bridge.available:
        console.print(f"[green]claude CLI found:[/green] {config.claude_bin}")
        console.print(f"[dim]Timeout: {config.timeout}s | Max turns: {config.max_turns}[/dim]")
    else:
        console.print("[red]claude CLI not found.[/red]")
        console.print(
            "[dim]Install Claude Code or set FLOWSTATE_CLAUDE_BIN to the binary path.[/dim]"
        )
