"""FlowState Orchestrator — sequences the Agentic Quadruple."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowstate.state import (
    FlowStateModel,
    ToolStatus,
    load_state,
    save_state,
    update_tool,
)
from flowstate.tools.autoresearch import AutoresearchAdapter
from flowstate.tools.gsd_adapter import GSDAdapter
from flowstate.tools.gstack import GstackAdapter
from flowstate.tools.superpowers import SuperpowersAdapter

console = Console()

TOOL_ORDER = ["autoresearch", "gstack", "gsd", "superpowers"]

STEP_LABELS = {
    "autoresearch": "Intelligence",
    "gstack": "Strategy",
    "gsd": "Management",
    "superpowers": "Discipline",
}


def _make_adapter(name: str, root: Path, dry_run: bool):
    adapters = {
        "autoresearch": AutoresearchAdapter,
        "gstack": GstackAdapter,
        "gsd": GSDAdapter,
        "superpowers": SuperpowersAdapter,
    }
    return adapters[name](root=root, dry_run=dry_run)


def run_pipeline(state: FlowStateModel, root: Path) -> FlowStateModel:
    dry_run = state.preferences.dry_run

    console.print()
    console.print(
        Panel(
            f"[bold]Running GrandSlam Pipeline[/bold]  "
            f"{'[yellow](dry-run)[/yellow]' if dry_run else '[green](live)[/green]'}",
            border_style="blue",
        )
    )

    # Step 1: Intelligence — Autoresearch
    console.print("\n[bold cyan]1/4 Intelligence[/] — Autoresearch")
    update_tool(state, "autoresearch", status=ToolStatus.RUNNING)
    save_state(state, root)

    ar = AutoresearchAdapter(root=root, dry_run=dry_run)
    result = ar.execute(state.interview)
    if result.success:
        update_tool(state, "autoresearch", status=ToolStatus.COMPLETED)
        for a in result.artifacts:
            update_tool(state, "autoresearch", artifact=a)
            state.artifacts["research_report"] = a
        console.print(f"  [green]{result.output}[/green]")
    else:
        update_tool(state, "autoresearch", status=ToolStatus.BLOCKED, error=result.error)
        console.print(f"  [red]Failed: {result.error}[/red]")

    save_state(state, root)

    # Step 2: Strategy — Gstack
    console.print("\n[bold yellow]2/4 Strategy[/] — Gstack")
    update_tool(state, "gstack", status=ToolStatus.RUNNING)
    save_state(state, root)

    gs = GstackAdapter(root=root, dry_run=dry_run)
    env_result = gs.init_stack()
    console.print(f"  [dim]env: {env_result.output}[/dim]")

    oh_result = gs.office_hours(state.interview)
    if oh_result.success:
        update_tool(state, "gstack", status=ToolStatus.COMPLETED)
        for a in oh_result.artifacts:
            update_tool(state, "gstack", artifact=a)
            state.artifacts["strategy_report"] = a
        console.print(f"  [green]{oh_result.output}[/green]")
    else:
        update_tool(state, "gstack", status=ToolStatus.BLOCKED, error=oh_result.error)
        console.print(f"  [red]Failed: {oh_result.error}[/red]")

    save_state(state, root)

    # Step 3: Management — GSD
    console.print("\n[bold green]3/4 Management[/] — GSD")
    update_tool(state, "gsd", status=ToolStatus.RUNNING)
    save_state(state, root)

    gsd = GSDAdapter(root=root, dry_run=dry_run)
    gsd_result = gsd.new_project(state.interview)
    if gsd_result.success:
        update_tool(state, "gsd", status=ToolStatus.COMPLETED)
        for a in gsd_result.artifacts:
            update_tool(state, "gsd", artifact=a)
            state.artifacts["roadmap"] = a
        console.print(f"  [green]{gsd_result.output}[/green]")
    else:
        update_tool(state, "gsd", status=ToolStatus.BLOCKED, error=gsd_result.error)
        console.print(f"  [red]Failed: {gsd_result.error}[/red]")

    save_state(state, root)

    # Step 4: Discipline — Superpowers
    console.print("\n[bold magenta]4/4 Discipline[/] — Superpowers")
    update_tool(state, "superpowers", status=ToolStatus.RUNNING)
    save_state(state, root)

    sp = SuperpowersAdapter(root=root, dry_run=dry_run)
    sp_result = sp.init_repo(state.interview)
    if sp_result.success:
        update_tool(state, "superpowers", status=ToolStatus.COMPLETED)
        console.print(f"  [green]{sp_result.output}[/green]")
    else:
        update_tool(state, "superpowers", status=ToolStatus.BLOCKED, error=sp_result.error)
        console.print(f"  [red]Failed: {sp_result.error}[/red]")

    save_state(state, root)

    console.print()
    console.print("[bold green]Pipeline complete.[/bold green]")
    return state


def print_status(root: Path) -> None:
    state = load_state(root)

    table = Table(title="FlowState Status", border_style="blue")
    table.add_column("Tool", style="bold")
    table.add_column("Phase")
    table.add_column("Status")
    table.add_column("Artifacts")
    table.add_column("Error")

    status_style = {
        ToolStatus.READY: "dim",
        ToolStatus.RUNNING: "yellow",
        ToolStatus.COMPLETED: "green",
        ToolStatus.BLOCKED: "red",
    }

    for name in TOOL_ORDER:
        ts = state.tools[name]
        style = status_style.get(ts.status, "")
        table.add_row(
            name,
            STEP_LABELS[name],
            f"[{style}]{ts.status.value}[/{style}]",
            ", ".join(ts.artifacts) or "—",
            ts.error or "—",
        )

    console.print()
    console.print(table)

    if state.artifacts:
        console.print("\n[bold]Artifacts:[/bold]")
        for key, path in state.artifacts.items():
            console.print(f"  {key}: {path}")

    console.print(f"\n[dim]Project: {state.preferences.project_name or '(not set)'}[/dim]")
    console.print(f"[dim]State file: {state_path_display(root)}[/dim]")


def state_path_display(root: Path) -> str:
    from flowstate.state import state_path
    return str(state_path(root))
