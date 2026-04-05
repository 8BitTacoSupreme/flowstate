"""FlowState CLI — entrypoint for the GrandSlam Orchestrator."""

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
    """FlowState — The GrandSlam Orchestrator."""


@main.command()
@click.option("--dry-run", is_flag=True, help="Simulate tool execution without calling real CLIs.")
@click.option("--root", type=click.Path(exists=True, path_type=Path), default=".", help="Project root directory.")
@click.option("--skip-interview", is_flag=True, help="Skip the interview and use existing state.")
def init(dry_run: bool, root: Path, skip_interview: bool):
    """Initialize a new FlowState project through the GrandSlam pipeline."""
    from flowstate.interview import run_interview
    from flowstate.orchestrator import run_pipeline
    from flowstate.state import load_state, save_state

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    state.preferences.dry_run = dry_run

    if not skip_interview:
        run_interview(state)
        save_state(state, root)

    run_pipeline(state, root)
    save_state(state, root)


@main.command()
@click.option("--root", type=click.Path(exists=True, path_type=Path), default=".", help="Project root directory.")
def status(root: Path):
    """Show the current state of the FlowState pipeline."""
    from flowstate.orchestrator import print_status

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    print_status(root)
