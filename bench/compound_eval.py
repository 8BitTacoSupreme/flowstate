"""Compounding-eval runner — argparse, K-run loop, mode dispatch, judge stub.

This is a developer/research tool, NOT a flowstate CLI subcommand. Invoke via:

    python -m bench.compound_eval --mode cheap --runs 5 --root bench/fixtures/sample_project

It drives the real FlowState substrate K times against a target project, captures
a RunSnapshot per run, computes the 4-axis scorecard, and renders a report whose
header carries the honest caveat (cheap mode validates the apparatus, not causation).

Modes:
  cheap (default, CI-safe, no network) — runs run_pipeline with dry_run=True against
    --root, mutating the project between runs to model convergence.
  real (research only, never CI) — runs run_pipeline live; requires explicit
    invocation. The thin live branch is intentionally minimal.

The --judge flag is SPEC-ONLY: it refuses unless --mode real plus --allow-llm and
NEVER lets judge output touch the mechanical score.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rich.console import Console

from bench.capture import capture_run_snapshot
from bench.metrics import RunSnapshot, Scorecard, compute_scorecard
from bench.project import mutate_for_run, scaffold
from bench.report import render_report, write_json

# Fixed probe so enrichment is measured against a stable query across runs.
_PROBE_QUERY = "core problem vision architecture compounding"

_console = Console()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench.compound_eval",
        description="Measure whether FlowState run N+1 beats run N on the same project.",
    )
    parser.add_argument("--mode", choices=("cheap", "real"), default="cheap")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument(
        "--allow-llm",
        action="store_true",
        help="Required (with --mode real) to even consider the spec-only judge.",
    )
    return parser


def _run_one(root: Path, *, dry_run: bool) -> None:
    """Drive the real substrate once. Imported lazily to keep import cost off the path."""
    from flowstate.orchestrator import run_pipeline
    from flowstate.state import load_state

    state = load_state(root)
    state.preferences.dry_run = dry_run
    run_pipeline(state, root)


def _cheap_loop(root: Path, runs: int, *, console: Console) -> Scorecard:
    """cheap-dry: run_pipeline dry K times, mutating between runs, capturing snapshots."""
    scaffold(root)
    snapshots: list[RunSnapshot] = []
    prior: RunSnapshot | None = None
    for i in range(runs):
        mutate_for_run(root, i)
        run_id = uuid4().hex[:12]
        window_start = datetime.now(UTC)
        try:
            _run_one(root, dry_run=True)
        except Exception as exc:  # never abort the loop on a substrate hiccup
            console.print(f"[yellow]run {i}: pipeline non-fatal error: {exc}[/yellow]")
        snap = capture_run_snapshot(
            root, _PROBE_QUERY, prior=prior, run_id=run_id, window_start=window_start
        )
        snapshots.append(snap)
        prior = snap
    return compute_scorecard(snapshots)


def _real_loop(root: Path, runs: int, *, console: Console) -> Scorecard:
    """real mode: run_pipeline live K times. Research-only; minimal by design."""
    snapshots: list[RunSnapshot] = []
    prior: RunSnapshot | None = None
    for _ in range(runs):
        run_id = uuid4().hex[:12]
        window_start = datetime.now(UTC)
        _run_one(root, dry_run=False)
        snap = capture_run_snapshot(
            root, _PROBE_QUERY, prior=prior, run_id=run_id, window_start=window_start
        )
        snapshots.append(snap)
        prior = snap
    return compute_scorecard(snapshots)


def _maybe_judge(args: argparse.Namespace, console: Console) -> None:
    """Guarded spec-only judge stub. Refuses unless --mode real + --allow-llm.

    NEVER produces a score and NEVER touches the mechanical scorecard.
    """
    if not args.judge:
        return
    if args.mode != "real" or not args.allow_llm:
        console.print(
            "[red]--judge is spec-only and NOT implemented. It requires --mode real "
            "AND --allow-llm to even be considered, and is excluded from the "
            "mechanical score regardless.[/red]"
        )
        return
    console.print(
        "[yellow]--judge is a specified-but-unimplemented Tier-2 stub. No LLM judging "
        "is performed; the mechanical scorecard above is authoritative.[/yellow]"
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    console = _console
    root = Path(args.root)
    runs = max(1, args.runs)

    if args.mode == "real":
        scorecard = _real_loop(root, runs, console=console)
    else:
        scorecard = _cheap_loop(root, runs, console=console)

    render_report(scorecard, console=console, markdown=args.markdown)
    _maybe_judge(args, console)

    if args.out is not None:
        write_json(scorecard, Path(args.out))
        console.print(f"[dim]wrote results: {args.out}[/dim]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
