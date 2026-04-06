"""FlowState Orchestrator — sequences context generation, research, strategy, and discipline."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowstate.bridge import BridgeConfig, ClaudeBridge
from flowstate.context import write_context_files
from flowstate.discipline import check_setup
from flowstate.launcher import print_next_steps
from flowstate.state import (
    FlowStateModel,
    ToolStatus,
    load_state,
    save_state,
    state_path,
    update_tool,
)
from flowstate.tools.gsd_adapter import GSDAdapter
from flowstate.tools.research import ResearchAdapter
from flowstate.tools.strategy import StrategyAdapter

console = Console()

TOOL_ORDER = ["research", "strategy", "gsd", "discipline"]

STEP_LABELS = {
    "research": "Research",
    "strategy": "Strategy",
    "gsd": "Management",
    "discipline": "Discipline",
}

STEP_STYLES = {
    "research": "cyan",
    "strategy": "yellow",
    "gsd": "green",
    "discipline": "magenta",
}


def _make_bridge(root: Path, dry_run: bool) -> ClaudeBridge:
    config = BridgeConfig(project_root=root)
    return ClaudeBridge(config=config, dry_run=dry_run)


def _run_step(
    state: FlowStateModel,
    root: Path,
    tool_name: str,
    step_num: int,
    total_steps: int,
    execute_fn,
) -> None:
    """Generic step runner with status tracking and output."""
    style = STEP_STYLES[tool_name]
    label = STEP_LABELS[tool_name]

    console.print(f"\n[bold {style}]{step_num}/{total_steps} {label}[/] — {tool_name}")
    update_tool(state, tool_name, status=ToolStatus.RUNNING)
    save_state(state, root)

    result = execute_fn()

    if result.success:
        update_tool(state, tool_name, status=ToolStatus.COMPLETED)
        for artifact in result.artifacts:
            update_tool(state, tool_name, artifact=artifact)
        console.print(f"  [green]{result.output[:300]}[/green]")
    else:
        update_tool(state, tool_name, status=ToolStatus.BLOCKED, error=result.error)
        console.print(f"  [red]Failed: {result.error}[/red]")

    save_state(state, root)
    return result


def run_pipeline(state: FlowStateModel, root: Path) -> FlowStateModel:
    dry_run = state.preferences.dry_run
    bridge = _make_bridge(root, dry_run)

    mode_tag = "[yellow](dry-run)[/yellow]" if dry_run else "[green](live)[/green]"
    if not dry_run and not bridge.available:
        mode_tag = "[red](no claude CLI — falling back to dry-run)[/red]"
        bridge = ClaudeBridge(config=bridge.config, dry_run=True)

    console.print()
    console.print(
        Panel(
            f"[bold]Running FlowState Pipeline[/bold]  {mode_tag}",
            border_style="blue",
        )
    )

    # Step 1: Context Generation — deterministic, <1s
    console.print("\n[bold blue]1/5 Context Generation[/] — deterministic")
    try:
        created = write_context_files(state, root)
        console.print(f"  [green]{len(created)} context files written[/green]")
        for p in created:
            console.print(f"    {p.relative_to(root)}")
    except Exception as e:
        console.print(f"  [red]Context generation failed: {e}[/red]")

    save_state(state, root)

    # Step 2: Research — split-topic bridge calls
    research = ResearchAdapter(root=root, dry_run=dry_run, bridge=bridge)
    result = _run_step(
        state, root, "research", 2, 5, lambda: research.execute(state.interview)
    )
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["research_report"] = a

    # Step 3: Strategy — single bridge call
    strategy = StrategyAdapter(root=root, dry_run=dry_run, bridge=bridge)
    result = _run_step(
        state, root, "strategy", 3, 5, lambda: strategy.pressure_test(state.interview)
    )
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["strategy_report"] = a

    # Step 4: Management — GSD context files (already written in step 1, this enriches)
    gsd = GSDAdapter(root=root, dry_run=dry_run, bridge=bridge)
    result = _run_step(state, root, "gsd", 4, 5, lambda: gsd.new_project(state))
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["roadmap"] = a

    # Step 5: Discipline — pure Python audit
    console.print("\n[bold magenta]5/5 Discipline[/] — audit")
    update_tool(state, "discipline", status=ToolStatus.RUNNING)
    save_state(state, root)

    audit = check_setup(root)
    update_tool(state, "discipline", status=ToolStatus.COMPLETED)
    console.print(f"  [green]{audit.summary}[/green]")
    save_state(state, root)

    console.print()
    _print_summary(state)

    # Show next steps
    print_next_steps(state, root)

    return state


def _print_summary(state: FlowStateModel) -> None:
    completed = sum(
        1 for ts in state.tools.values() if ts.status == ToolStatus.COMPLETED
    )
    blocked = sum(1 for ts in state.tools.values() if ts.status == ToolStatus.BLOCKED)

    if blocked == 0:
        console.print(
            "[bold green]Pipeline complete. All steps succeeded.[/bold green]"
        )
    else:
        console.print(
            f"[bold yellow]Pipeline finished: {completed}/{len(state.tools)} succeeded, "
            f"{blocked} blocked.[/bold yellow]"
        )

    if state.context_files:
        console.print("\n[bold]Context files:[/bold]")
        for f in state.context_files:
            console.print(f"  {f}")


def run_phase(state: FlowStateModel, root: Path, phase: int) -> FlowStateModel:
    """Print the launch command for a GSD phase.

    Phases now run natively inside Claude Code sessions.
    Use `flowstate launch gsd <phase>` for the exact command.
    """
    from flowstate.launcher import launch_command

    console.print(f"\n[bold blue]Phase {phase} — Native Execution[/bold blue]")
    console.print(
        "\n[yellow]GSD phases run natively inside Claude Code sessions.[/yellow]"
        "\nUse the following command:\n"
    )

    cmd = launch_command("gsd", phase, root)
    console.print(f"  [cyan]{cmd}[/cyan]")
    console.print()

    save_state(state, root)
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
        ts = state.tools.get(name)
        if ts is None:
            continue
        style = status_style.get(ts.status, "")
        table.add_row(
            name,
            STEP_LABELS.get(name, name),
            f"[{style}]{ts.status.value}[/{style}]",
            ", ".join(ts.artifacts) or "---",
            ts.error or "---",
        )

    console.print()
    console.print(table)

    if state.context_files:
        console.print("\n[bold]Context files:[/bold]")
        for f in state.context_files:
            console.print(f"  {f}")

    if state.artifacts:
        console.print("\n[bold]Artifacts:[/bold]")
        for key, path in state.artifacts.items():
            console.print(f"  {key}: {path}")

    console.print(
        f"\n[dim]Project: {state.preferences.project_name or '(not set)'}[/dim]"
    )
    console.print(f"[dim]State file: {state_path(root)}[/dim]")
