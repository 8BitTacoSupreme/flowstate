"""Compounding-eval runner — argparse, K-run loop, mode dispatch, judge stub.

This is a developer/research tool, NOT a flowstate CLI subcommand. Invoke via:

    python -m bench.compound_eval --mode cheap --runs 5 --root bench/fixtures/sample_project

It drives the real FlowState substrate K times against a target project, captures
a RunSnapshot per run, computes the 4-axis scorecard, and renders a report whose
header carries the honest caveat (cheap mode validates the apparatus, not causation).

Isolation: the runner NEVER writes into the source ``--root``. It copies the root
into a fresh ``tempfile.mkdtemp()`` working directory (via ``shutil.copytree``) and
runs ALL K iterations there, then removes the temp dir (best-effort, never raises).
The source fixture therefore stays byte-for-byte pristine — pointing ``--root`` at a
checked-in fixture is safe and leaves ``git status`` clean.

Modes:
  cheap (default, CI-safe, no network) — runs run_pipeline with dry_run=True against
    a temp copy of --root, mutating the project between runs so all four axes move.
  real (research only, never CI) — runs run_pipeline live against a temp copy. It
    requires a usable claude bridge and fails fast with a clear message when one is
    absent (rather than silently degrading to dry-run / cheap behavior).

The --judge flag is SPEC-ONLY: it refuses unless --mode real plus --allow-llm and
NEVER lets judge output touch the mechanical score.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rich.console import Console

from bench.capture import capture_run_snapshot
from bench.judge import JudgeResult, collect_artifacts, judge_run
from bench.metrics import RunSnapshot, Scorecard, compute_scorecard
from bench.project import mutate_for_run, scaffold
from bench.report import render_judge_panel, render_report, write_json

# Fixed probe so enrichment is measured against a stable query across runs.
_PROBE_QUERY = "core problem vision architecture compounding"

_console = Console()

# Maps --layers CLI choice to the include_layers frozenset for build_context_prefix.
# full   -> None            : all layers (no patch — call run_pipeline directly)
# none   -> frozenset()     : empty prefix (== old inject=off control arm)
# pack   -> frozenset({"fixtures","pack"})                        : RAG layers only
# memory -> frozenset({"gotchas","memory","since_last_run"})      : compounding layers only
_LAYERS_MAP: dict[str, frozenset[str] | None] = {
    "full": None,
    "none": frozenset(),
    "pack": frozenset({"fixtures", "pack"}),
    "memory": frozenset({"gotchas", "memory", "since_last_run"}),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bench.compound_eval",
        description="Measure whether FlowState run N+1 beats run N on the same project.",
    )
    parser.add_argument("--mode", choices=("cheap", "real"), default="cheap")
    parser.add_argument(
        "--layers",
        choices=("full", "none", "pack", "memory"),
        default="full",
        help=(
            "real mode: per-layer context attribution. "
            "full=all layers (default), "
            "none=control arm (empty prefix, isolates compounding), "
            "pack=fixtures+pack (RAG only), "
            "memory=gotchas+memory+since_last_run (compounding only)."
        ),
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument(
        "--allow-llm",
        action="store_true",
        help="Required (with --mode real --judge) to enable the Tier-2 output-quality judge.",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model for the Tier-2 judge (default: claude CLI's default model).",
    )
    return parser


@contextlib.contextmanager
def _worktree(root: Path) -> Iterator[Path]:
    """Copy ``root`` into a fresh temp dir and yield the copy; clean up at exit.

    The source ``root`` is never written to — all iterations run in the copy.
    Cleanup is best-effort and never raises, matching never-raises discipline.
    """
    work = Path(tempfile.mkdtemp(prefix="bench_compound_"))
    target = work / "proj"
    try:
        shutil.copytree(root, target, dirs_exist_ok=True)
        yield target
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _bridge_available() -> bool:
    """True iff a real claude CLI is locatable (gates --mode real). Never raises.

    Replicates flowstate.bridge's locator using stdlib only — bench deliberately
    does NOT import flowstate.bridge, to stay decoupled from the LLM substrate.
    """
    try:
        env_path = os.environ.get("FLOWSTATE_CLAUDE_BIN")
        if env_path and Path(env_path).is_file():
            return True
        if shutil.which("claude"):
            return True
        candidates = (
            Path.home() / ".local" / "bin" / "claude",
            Path("/usr/local/bin/claude"),
            Path("/opt/homebrew/bin/claude"),
        )
        return any(c.is_file() for c in candidates)
    except Exception:
        return False


def _run_one(root: Path, *, dry_run: bool, layers: str = "full") -> None:
    """Drive the real substrate once. Imported lazily to keep import cost off the path.

    When ``layers`` is not "full", the context prefix is filtered at assembly time
    via the ``include_layers`` kwarg injected into ``build_context_prefix``.  The
    pipeline still accumulates memory on disk, but the LLM only SEES the selected
    layers — enabling per-layer A/B attribution.

    ``layers="none"`` is the control arm: all prior-knowledge injection suppressed
    (equivalent to the old ``inject=False`` behaviour).  ``layers="full"`` (default)
    calls ``run_pipeline`` directly without any monkeypatch.
    """
    import flowstate.orchestrator as orch
    from flowstate.state import load_state

    state = load_state(root)
    state.preferences.dry_run = dry_run

    include = _LAYERS_MAP[layers]
    if include is None:
        # full arm — no patch, run directly
        orch.run_pipeline(state, root)
        return

    # Non-full arm: wrap build_context_prefix to inject include_layers
    original = orch.build_context_prefix

    def _wrapped(*a, **k):
        k.setdefault("include_layers", include)
        return original(*a, **k)

    orch.build_context_prefix = _wrapped
    try:
        orch.run_pipeline(state, root)
    finally:
        orch.build_context_prefix = original


def _cheap_loop(root: Path, runs: int, *, console: Console) -> Scorecard:
    """cheap-dry: run_pipeline dry K times in a temp copy, mutating between runs.

    Never touches the source ``root`` — all work happens in an isolated copy.
    """
    snapshots: list[RunSnapshot] = []
    prior: RunSnapshot | None = None
    with _worktree(root) as target:
        scaffold(target)
        for i in range(runs):
            mutate_for_run(target, i)
            run_id = uuid4().hex[:12]
            window_start = datetime.now(UTC)
            try:
                _run_one(target, dry_run=True)
            except Exception as exc:  # never abort the loop on a substrate hiccup
                console.print(f"[yellow]run {i}: pipeline non-fatal error: {exc}[/yellow]")
            snap = capture_run_snapshot(
                target, _PROBE_QUERY, prior=prior, run_id=run_id, window_start=window_start
            )
            snapshots.append(snap)
            prior = snap
    return compute_scorecard(snapshots)


def _load_fixture(root: Path) -> dict:
    """Read the run's starter fixture (system_contract/retrieval_questions). Never raises."""
    try:
        return json.loads((root / ".planning" / "fixtures" / "starter.json").read_text())
    except Exception:
        return {}


def _real_loop(
    root: Path,
    runs: int,
    *,
    console: Console,
    do_judge: bool = False,
    judge_model: str | None = None,
    layers: str = "full",
) -> tuple[Scorecard, list[JudgeResult]]:
    """real mode: run_pipeline live K times in a temp copy. Research-only.

    Fails fast (empty scorecard, clear message) when no claude bridge is available,
    rather than silently behaving like cheap mode. Never touches the source root.
    When ``do_judge`` is set, scores each run's produced artifacts (Tier-2, excluded
    from the mechanical scorecard).
    """
    if not _bridge_available():
        console.print(
            "[red]--mode real requires a usable claude bridge (claude CLI on PATH or "
            "FLOWSTATE_CLAUDE_BIN set); none was found. Refusing to run real mode — it "
            "would silently degrade to dry-run. Use --mode cheap for the CI-safe path.[/red]"
        )
        return compute_scorecard([]), []

    snapshots: list[RunSnapshot] = []
    judged: list[JudgeResult] = []
    prior: RunSnapshot | None = None
    with _worktree(root) as target:
        scaffold(target)
        fixture = _load_fixture(target)
        for i in range(runs):
            # Real mode does NOT mutate between runs: the project is held fixed so the
            # ONLY variable across runs is FlowState's accumulating memory/journal/gotchas
            # (the compounding hypothesis). Scripted mutation would conflate that signal
            # — it belongs to cheap mode, where it models a converging project.
            run_id = uuid4().hex[:12]
            window_start = datetime.now(UTC)
            try:
                _run_one(target, dry_run=False, layers=layers)
            except Exception as exc:  # never abort the loop on a substrate hiccup
                console.print(f"[yellow]run {i}: pipeline non-fatal error: {exc}[/yellow]")
            snap = capture_run_snapshot(
                target, _PROBE_QUERY, prior=prior, run_id=run_id, window_start=window_start
            )
            snapshots.append(snap)
            prior = snap
            if do_judge:
                judged.append(judge_run(i, collect_artifacts(target), fixture, model=judge_model))
                console.print(f"[dim]run {i}: judged output quality = {judged[-1].score}[/dim]")
    return compute_scorecard(snapshots), judged


def _judge_allowed(args: argparse.Namespace, console: Console) -> bool:
    """Whether the Tier-2 judge runs. Requires --judge AND --mode real AND --allow-llm.

    Prints a clear refusal when --judge is requested but the gate is not met. The judge
    is ALWAYS excluded from the mechanical CompoundingScore.
    """
    if not args.judge:
        return False
    if args.mode != "real" or not args.allow_llm:
        console.print(
            "[red]--judge requires --mode real AND --allow-llm (it makes live LLM calls "
            "and is excluded from the mechanical score). Skipping the judge.[/red]"
        )
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    console = _console
    root = Path(args.root)
    runs = max(1, args.runs)
    do_judge = _judge_allowed(args, console)

    judged: list[JudgeResult] = []
    if args.mode == "real":
        scorecard, judged = _real_loop(
            root,
            runs,
            console=console,
            do_judge=do_judge,
            judge_model=args.judge_model,
            layers=args.layers,
        )
    else:
        scorecard = _cheap_loop(root, runs, console=console)

    render_report(scorecard, console=console, markdown=args.markdown)
    if judged:
        render_judge_panel(judged, console=console)

    if args.out is not None:
        # never-raises: an unwritable --out degrades to a warning, not a crash.
        try:
            write_json(scorecard, Path(args.out), judge_results=judged or None)
            console.print(f"[dim]wrote results: {args.out}[/dim]")
        except OSError as exc:
            console.print(f"[red]could not write results to {args.out}: {exc}[/red]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
