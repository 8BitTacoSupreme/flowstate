"""FlowState CLI — entrypoint for the context orchestrator."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from flowstate import __version__
from flowstate.config import (
    clear_default_root,
    load_default_root,
    resolve_root,
    save_default_root,
)

console = Console()

BANNER = r"""
  _____ _              ____  _        _
 |  ___| | _____      / ___|| |_ __ _| |_ ___
 | |_  | |/ _ \ \ /\ / /\___ \| __/ _` | __/ _ \
 |  _| | | (_) \ V  V /  ___) | || (_| | ||  __/
 |_|   |_|\___/ \_/\_/  |____/ \__\__,_|\__\___|
"""


def _root_was_explicit() -> bool:
    """Check if --root was passed on the command line."""
    ctx = click.get_current_context()
    return ctx.get_parameter_source("root") == click.core.ParameterSource.COMMANDLINE


@click.group()
@click.version_option(__version__, prog_name="flowstate")
def main():
    """FlowState — The Context Orchestrator."""


@main.command()
@click.option("--dry-run", is_flag=True, help="Simulate tool execution without calling real CLIs.")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
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
    root: Path | None,
    skip_interview: bool,
    model: str | None,
    budget: float | None,
    effort: str | None,
):
    """Initialize a new FlowState project through the pipeline."""
    from flowstate.interview import run_interview
    from flowstate.orchestrator import run_pipeline
    from flowstate.state import load_state, save_state

    explicit = _root_was_explicit()
    root = resolve_root(root, option_was_explicit=explicit)

    if explicit:
        save_default_root(root)

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


@main.command("kickoff")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option("--skip-interview", is_flag=True, help="Skip the interview and use existing state.")
def kickoff(root: Path | None, skip_interview: bool):
    """Scaffold a new project without running the LLM pipeline.

    Runs the interview (unless --skip-interview), writes deterministic context files,
    generates the repomix pack, and saves state. No bridge or LLM calls are made.
    """
    from flowstate.context import write_context_files
    from flowstate.interview import run_interview
    from flowstate.pack import run_pack
    from flowstate.state import load_state, save_state

    explicit = _root_was_explicit()
    root = resolve_root(root, option_was_explicit=explicit)

    if explicit:
        save_default_root(root)

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)

    if not skip_interview:
        run_interview(state)
        save_state(state, root)

    created = write_context_files(state, root)

    pack_result = run_pack(root)
    if pack_result.success:
        rel = pack_result.output_path.relative_to(root)
        console.print(f"[green]Pack written:[/green] {rel}")
    else:
        console.print(f"[yellow]Pack skipped:[/yellow] {pack_result.error}")

    save_state(state, root)

    console.print(f"\n[green]{len(created)} context files scaffolded:[/green]")
    for p in created:
        console.print(f"  {p.relative_to(root)}")
    console.print()


@main.command()
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option(
    "--markdown",
    is_flag=True,
    help="Render as markdown (cross-session handoff format) instead of Rich table.",
)
@click.option(
    "--write",
    "write_path",
    type=click.Path(path_type=Path),
    default=None,
    is_flag=False,
    flag_value="status.md",
    help="Write markdown to PATH (default: status.md in cwd). Implies --markdown.",
)
def status(root: Path | None, markdown: bool, write_path: Path | None):
    """Show the current state of the FlowState pipeline.

    Default output is a Rich table. Use --markdown for cross-session handoff
    format; --write PATH writes the markdown to a file.
    """
    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    # --write implies --markdown
    if write_path is not None:
        markdown = True

    if markdown:
        from flowstate.state import load_state
        from flowstate.status_markdown import render_status_markdown

        state = load_state(root)
        rendered = render_status_markdown(state, root)

        if write_path is not None:
            target = Path(write_path)
            if not target.is_absolute():
                target = Path.cwd() / target
            target.write_text(rendered)
            # Use click.echo (not Rich) so long absolute paths don't get soft-wrapped
            click.echo(f"Wrote: {target.resolve()}")
        else:
            # Print raw markdown without Rich formatting so pipes/redirects work cleanly
            click.echo(rendered)
        return

    # Default Rich-table path (unchanged behavior)
    from flowstate.orchestrator import print_status

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    print_status(root)


@main.command()
@click.argument("phase", type=int)
@click.option("--dry-run", is_flag=True, help="Simulate execution.")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
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
    root: Path | None,
    model: str | None,
    budget: float | None,
    effort: str | None,
):
    """Run a specific GSD phase (prints native session command)."""
    from flowstate.orchestrator import run_phase
    from flowstate.state import load_state, save_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

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
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def launch(tool: str, phase: int | None, root: Path | None):
    """Print the native Claude Code command for a tool.

    Examples:
        flowstate launch gsd 1      — Print /gsd:plan-phase 1 command
        flowstate launch gsd        — Print /gsd:progress command
    """
    from flowstate.launcher import launch_command

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    cmd = launch_command(tool, phase, root)
    console.print("\n[bold]Launch command:[/bold]\n")
    console.print(f"  [cyan]{cmd}[/cyan]")
    console.print()


@main.command("context")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def context(root: Path | None):
    """Regenerate context files from current state."""
    from flowstate.context import write_context_files
    from flowstate.state import load_state, save_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

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
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def memory_search(query: str, kind: str | None, limit: int, root: Path | None):
    """Search stored memories via full-text search."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

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
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def memory_stats(root: Path | None):
    """Show memory counts by kind."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

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
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def memory_clear(root: Path | None, yes: bool):
    """Delete all stored memories."""
    from flowstate.memory import MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    if not yes and not click.confirm("Delete all memories? This cannot be undone"):
        console.print("[dim]Cancelled.[/dim]")
        return

    store = MemoryStore(root=root)
    deleted = store.clear()
    store.close()
    console.print(f"[green]Cleared {deleted} memories.[/green]")


main.add_command(memory)


def _scan_orphans(root: Path, manifest_paths: set[Path]) -> list[Path]:
    """Return files in .planning/ + research/ + memory.db + flowstate.json not in manifest."""
    candidates: list[Path] = []
    for sub in (".planning", "research"):
        base = root / sub
        if base.is_dir():
            candidates.extend(p for p in base.rglob("*") if p.is_file())
    mem = root / "memory.db"
    if mem.exists():
        candidates.append(mem)
    state_file = root / "flowstate.json"
    if state_file.exists():
        candidates.append(state_file)
    return [p for p in candidates if p.resolve() not in manifest_paths]


def _verify_checksum(path: Path, expected: str | None) -> bool:
    """True if the file's sha256 matches expected. None expected always returns True."""
    if expected is None:
        return True
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest() == expected


@main.command()
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.option("--force", is_flag=True, help="Also remove orphan files (not in manifest).")
def fresh(root: Path | None, yes: bool, force: bool):
    """Remove FlowState-owned files per install_manifest.

    Files tracked in the manifest are removed. Files in .planning/ / research/
    that aren't in the manifest are reported as orphans and left in place
    unless --force is passed.
    """
    import shutil

    from flowstate.state import load_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    # Guard: no state file → empty manifest (fresh project, nothing to do via manifest).
    # load_state(root) raises if flowstate.json is missing — DO NOT call it unguarded.
    state_path = root / "flowstate.json"
    if state_path.exists():
        state = load_state(root)
        manifest = state.install_manifest
    else:
        manifest = []

    manifest_paths = {(root / e.path).resolve() for e in manifest}
    manifest_present = [(root / e.path, e) for e in manifest if (root / e.path).exists()]
    orphans = _scan_orphans(root, manifest_paths)

    if not manifest_present and not orphans:
        console.print("[dim]Nothing to clean — project is already fresh.[/dim]")
        return

    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))
    if manifest_present:
        console.print("[bold]Manifest-owned files (will be removed):[/bold]")
        for p, entry in manifest_present:
            warn = "" if _verify_checksum(p, entry.checksum) else " [yellow](modified)[/yellow]"
            console.print(f"  [file] {p.relative_to(root)}{warn}")
    if orphans:
        label = "will be removed (--force)" if force else "left in place (use --force to remove)"
        console.print(f"\n[bold]Orphans (not in manifest) — {label}:[/bold]")
        for p in orphans:
            console.print(f"  [orphan] {p.relative_to(root)}")

    if not yes and not click.confirm("\nProceed?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    removed = 0
    for p, _entry in manifest_present:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        removed += 1
    if force:
        for p in orphans:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            removed += 1

    # Sweep empty subdirectories inside .planning/ and research/ (and the dirs themselves)
    for sub in (".planning", "research"):
        base = root / sub
        if not base.is_dir():
            continue
        # Walk leaves-up so nested empty dirs get pruned
        for p in sorted(base.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        if base.is_dir() and not any(base.iterdir()):
            base.rmdir()
            console.print(f"  [dim]Removed empty {sub}/[/dim]")

    console.print(f"\n[green]Removed {removed} items. Ready for flowstate init.[/green]")


@main.command("journal")
@click.option("--limit", type=int, default=10, help="Max entries to show (default: 10).")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def journal(limit: int, root: Path | None):
    """List recent run-journal entries, newest first."""
    from rich.table import Table

    from flowstate.memory import MemoryKind, MemoryStore

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    try:
        store = MemoryStore(root=root)
        entries = store.get_by_kind(MemoryKind.RUN, limit=limit)
        store.close()
    except Exception:
        console.print("[dim]no journal entries yet[/dim]")
        return

    if not entries:
        console.print("[dim]no journal entries yet[/dim]")
        return

    table = Table(title="Run Journal", border_style="blue")
    table.add_column("Run ID", style="dim", width=12)
    table.add_column("Timestamp", width=24)
    table.add_column("Delta", min_width=40)
    table.add_column("Dry Run", width=8)

    for entry in entries:
        meta = entry.metadata
        table.add_row(
            entry.run_id,
            entry.created_at.isoformat()[:19],
            meta.get("delta_line", entry.summary),
            "yes" if meta.get("dry_run") else "no",
        )

    console.print(table)


@main.command("pack")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option("--compress", is_flag=True, help="Pass --compress to repomix (reduces token count).")
@click.option("--force", is_flag=True, help="Repack even when the existing pack is up to date.")
def pack(root: Path | None, compress: bool, force: bool):
    """Generate the repomix codebase pack at .planning/codebase/repomix-pack.xml.

    Skips regeneration when the pack is up to date (no source file is newer than
    the pack's install_manifest entry). Use --force to repack unconditionally.

    Exits non-zero with a clear message when repomix is not found on PATH and
    FLOWSTATE_REPOMIX_BIN is not set.
    """
    import sys

    from flowstate.pack import is_pack_stale, run_pack
    from flowstate.state import load_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())
    state = load_state(root)

    has_pack_entry = any(
        e.path == ".planning/codebase/repomix-pack.xml" for e in state.install_manifest
    )
    if not force and has_pack_entry and not is_pack_stale(root, state):
        console.print("[dim]Pack up to date; skipping (use --force to repack).[/dim]")
        return

    result = run_pack(root, compress=compress)
    if result.success:
        rel = result.output_path.relative_to(root)
        console.print(f"[green]Pack written:[/green] {rel}")
    else:
        console.print(f"[red]{result.error}[/red]")
        sys.exit(1)


@main.command("check")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def check_bridge(root: Path | None):
    """Check if the claude CLI bridge is available and configured."""
    from flowstate.bridge import BridgeConfig, ClaudeBridge

    root = resolve_root(root, option_was_explicit=_root_was_explicit())

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


@main.command("doctor")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
def doctor(root: Path | None):
    """Run health checks against the FlowState install.

    Exits non-zero (count of error-severity findings) so it composes
    in CI / pre-commit hooks.
    """
    import sys

    from rich.table import Table

    from flowstate.doctor import run_doctor
    from flowstate.state import load_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())
    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    findings = run_doctor(state, root)

    if not findings:
        console.print("[green]All checks passed.[/green]")
        return

    table = Table(title="flowstate doctor", border_style="blue")
    table.add_column("Check", style="bold")
    table.add_column("Severity")
    table.add_column("Message")
    sev_style = {"error": "red", "warning": "yellow", "info": "dim"}
    for d in findings:
        style = sev_style.get(d.severity, "white")
        table.add_row(
            d.name,
            f"[{style}]{d.severity}[/{style}]",
            d.message,
        )
    console.print(table)

    errors = sum(1 for d in findings if d.severity == "error")
    warnings = sum(1 for d in findings if d.severity == "warning")
    console.print(f"\n[bold]Summary:[/bold] {errors} error(s), {warnings} warning(s)")
    if errors:
        sys.exit(errors)


@main.command("repair")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    default=None,
    help="Project root directory.",
)
@click.option(
    "--apply-destructive",
    is_flag=True,
    help="Also apply destructive fixes (delete orphans, recreate corrupt memory.db).",
)
def repair(root: Path | None, apply_destructive: bool):
    """Apply safe fixes for doctor findings; destructive fixes require --apply-destructive."""
    from flowstate.doctor import run_doctor
    from flowstate.repair import apply_destructive_fixes, apply_safe_fixes
    from flowstate.state import load_state, save_state

    root = resolve_root(root, option_was_explicit=_root_was_explicit())
    console.print(Panel(BANNER, title="v" + __version__, border_style="blue", expand=False))

    state = load_state(root)
    findings = run_doctor(state, root)
    if not findings:
        console.print("[green]Nothing to repair — all checks passed.[/green]")
        return

    safe = apply_safe_fixes(state, root, findings)
    if safe:
        console.print(f"[green]Applied {len(safe)} safe fix(es):[/green]")
        for line in safe:
            console.print(f"  - {line}")
    else:
        console.print("[dim]No safe fixes applied.[/dim]")

    if apply_destructive:
        destructive = apply_destructive_fixes(state, root, findings)
        if destructive:
            console.print(f"[yellow]Applied {len(destructive)} destructive fix(es):[/yellow]")
            for line in destructive:
                console.print(f"  - {line}")
        else:
            console.print("[dim]No destructive fixes applied.[/dim]")
    else:
        destructive_pending = [
            d for d in findings if d.name == "orphan_files" or "unreadable" in d.message.lower()
        ]
        if destructive_pending:
            console.print(
                f"\n[dim]{len(destructive_pending)} destructive fix(es) skipped. "
                "Re-run with --apply-destructive.[/dim]"
            )

    save_state(state, root)


# ── config subgroup ─────────────────────────────────────────────────


@main.group("config")
def config_group():
    """Manage FlowState global configuration."""


@config_group.command("show")
def config_show():
    """Display current configuration."""
    saved = load_default_root()
    if saved:
        console.print(f"[bold]default_root[/bold] = {saved}")
    else:
        console.print("[dim]No default root configured.[/dim]")


@config_group.command("set-root")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def config_set_root(path: Path):
    """Set the default project root directory."""
    save_default_root(path)
    console.print(f"[green]Default root set to:[/green] {path.resolve()}")


@config_group.command("clear-root")
def config_clear_root():
    """Remove the saved default root."""
    if clear_default_root():
        console.print("[green]Default root cleared.[/green]")
    else:
        console.print("[dim]No default root was configured.[/dim]")
