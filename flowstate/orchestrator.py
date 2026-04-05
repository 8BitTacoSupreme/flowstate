"""FlowState Orchestrator — sequences the Agentic Quadruple."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from flowstate.bridge import BridgeConfig, ClaudeBridge
from flowstate.state import (
    FlowStateModel,
    ToolStatus,
    load_state,
    save_state,
    state_path,
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

STEP_STYLES = {
    "autoresearch": "cyan",
    "gstack": "yellow",
    "gsd": "green",
    "superpowers": "magenta",
}


def _make_bridge(root: Path, dry_run: bool) -> ClaudeBridge:
    config = BridgeConfig(project_root=root)
    return ClaudeBridge(config=config, dry_run=dry_run)


def _run_step(
    state: FlowStateModel,
    root: Path,
    tool_name: str,
    step_num: int,
    execute_fn,
) -> None:
    """Generic step runner with status tracking and output."""
    style = STEP_STYLES[tool_name]
    label = STEP_LABELS[tool_name]

    console.print(f"\n[bold {style}]{step_num}/4 {label}[/] — {tool_name}")
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
            f"[bold]Running GrandSlam Pipeline[/bold]  {mode_tag}",
            border_style="blue",
        )
    )

    # Step 1: Intelligence — Autoresearch
    ar = AutoresearchAdapter(root=root, dry_run=dry_run, bridge=bridge)
    result = _run_step(state, root, "autoresearch", 1, lambda: ar.execute(state.interview))
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["research_report"] = a

    # Step 2: Strategy — Gstack
    gs = GstackAdapter(root=root, dry_run=dry_run, bridge=bridge)

    def _gstack_combined():
        env_result = gs.init_stack()
        console.print(f"  [dim]env: {env_result.output[:200]}[/dim]")
        return gs.office_hours(state.interview)

    result = _run_step(state, root, "gstack", 2, _gstack_combined)
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["strategy_report"] = a

    # Step 3: Management — GSD
    gsd = GSDAdapter(root=root, dry_run=dry_run, bridge=bridge)
    result = _run_step(state, root, "gsd", 3, lambda: gsd.new_project(state.interview))
    if result and result.success:
        for a in result.artifacts:
            state.artifacts["roadmap"] = a

    # Step 4: Discipline — Superpowers
    sp = SuperpowersAdapter(root=root, dry_run=dry_run, bridge=bridge)
    _run_step(state, root, "superpowers", 4, lambda: sp.init_repo(state.interview))

    console.print()
    _print_summary(state)
    return state


def _print_summary(state: FlowStateModel) -> None:
    completed = sum(1 for ts in state.tools.values() if ts.status == ToolStatus.COMPLETED)
    blocked = sum(1 for ts in state.tools.values() if ts.status == ToolStatus.BLOCKED)

    if blocked == 0:
        console.print("[bold green]Pipeline complete. All 4 tools succeeded.[/bold green]")
    else:
        console.print(
            f"[bold yellow]Pipeline finished: {completed}/4 succeeded, "
            f"{blocked} blocked.[/bold yellow]"
        )


def run_phase(state: FlowStateModel, root: Path, phase: int) -> FlowStateModel:
    """Run a specific GSD phase (plan + execute)."""
    dry_run = state.preferences.dry_run
    bridge = _make_bridge(root, dry_run)
    gsd = GSDAdapter(root=root, dry_run=dry_run, bridge=bridge)
    sp = SuperpowersAdapter(root=root, dry_run=dry_run, bridge=bridge)

    console.print(f"\n[bold blue]Running Phase {phase}[/bold blue]")

    # Check if this phase needs worktree isolation
    milestones = state.interview.milestones
    phase_label = milestones[phase - 1] if phase <= len(milestones) else f"Phase {phase}"
    if sp.should_branch(phase_label):
        console.print(f"  [yellow]Hardening detected — creating worktree branch[/yellow]")
        branch = f"phase-{phase}-{phase_label.lower().replace(' ', '-')}"
        wt_result = sp.create_worktree(branch)
        console.print(f"  [dim]{wt_result.output}[/dim]")

    # Plan
    console.print(f"  [cyan]Planning phase {phase}...[/cyan]")
    plan_result = gsd.plan_phase(phase)
    if plan_result.success:
        console.print(f"  [green]Plan created[/green]")
    else:
        console.print(f"  [red]Planning failed: {plan_result.error}[/red]")
        return state

    # Execute
    console.print(f"  [cyan]Executing phase {phase}...[/cyan]")
    exec_result = gsd.execute_phase(phase)
    if exec_result.success:
        console.print(f"  [green]Phase {phase} complete[/green]")
    else:
        console.print(f"  [red]Execution failed: {exec_result.error}[/red]")

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
        ts = state.tools[name]
        style = status_style.get(ts.status, "")
        table.add_row(
            name,
            STEP_LABELS[name],
            f"[{style}]{ts.status.value}[/{style}]",
            ", ".join(ts.artifacts) or "---",
            ts.error or "---",
        )

    console.print()
    console.print(table)

    if state.artifacts:
        console.print("\n[bold]Artifacts:[/bold]")
        for key, path in state.artifacts.items():
            console.print(f"  {key}: {path}")

    console.print(f"\n[dim]Project: {state.preferences.project_name or '(not set)'}[/dim]")
    console.print(f"[dim]State file: {state_path(root)}[/dim]")
