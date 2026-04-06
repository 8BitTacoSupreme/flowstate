"""FlowState CLI — entrypoint for the context orchestrator."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from flowstate import __version__

console = Console()

BANNER = r"""
 _____ _            ____  _        _
|  ___| | _____  __/ ___|| |_ __ _| |_ ___
| |_  | |/ _ \ \/ /\___ \| __/ _` | __/ _ \
|  _| | | (_) >  <  ___) | || (_| | ||  __/
|_|   |_|\___/_/\_\|____/ \__\__,_|\__\___|
"""


@click.group()
@click.version_option(__version__, prog_name="flowstate")
def main():
    """FlowState — The Context Orchestrator."""


@main.command()
@click.option(
    "--dry-run", is_flag=True, help="Simulate tool execution without calling real CLIs."
)
@click.option(
    "--root",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Project root directory.",
)
@click.option(
    "--skip-interview", is_flag=True, help="Skip the interview and use existing state."
)
def init(dry_run: bool, root: Path, skip_interview: bool):
    """Initialize a new FlowState project through the pipeline."""
    from flowstate.interview import run_interview
    from flowstate.orchestrator import run_pipeline
    from flowstate.state import load_state, save_state

    console.print(
        Panel(BANNER, title="v" + __version__, border_style="blue", expand=False)
    )

    state = load_state(root)
    state.preferences.dry_run = dry_run

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

    console.print(
        Panel(BANNER, title="v" + __version__, border_style="blue", expand=False)
    )
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
def run(phase: int, dry_run: bool, root: Path):
    """Run a specific GSD phase (prints native session command)."""
    from flowstate.orchestrator import run_phase
    from flowstate.state import load_state, save_state

    state = load_state(root)
    state.preferences.dry_run = dry_run

    console.print(
        Panel(BANNER, title="v" + __version__, border_style="blue", expand=False)
    )
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

    console.print(
        Panel(BANNER, title="v" + __version__, border_style="blue", expand=False)
    )
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

    console.print(
        Panel(BANNER, title="v" + __version__, border_style="blue", expand=False)
    )

    state = load_state(root)
    created = write_context_files(state, root)
    save_state(state, root)

    console.print(f"\n[green]{len(created)} context files written:[/green]")
    for p in created:
        console.print(f"  {p.relative_to(root)}")
    console.print()


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
        console.print(
            f"[dim]Timeout: {config.timeout}s | Max turns: {config.max_turns}[/dim]"
        )
    else:
        console.print("[red]claude CLI not found.[/red]")
        console.print(
            "[dim]Install Claude Code or set FLOWSTATE_CLAUDE_BIN "
            "to the binary path.[/dim]"
        )
