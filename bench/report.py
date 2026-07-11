"""Report rendering for the compounding harness — JSON + Rich + the honest caveat.

``write_json`` serializes a ``Scorecard`` deterministically (``sort_keys`` +
indent) so result diffs are reviewable. ``render_report`` prints the mandatory
honest caveat FIRST, then a per-run trend table (mirroring the flowstate verify
Rich-table idiom) and a scorecard panel.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bench.judge import JudgeResult, summarize
from bench.metrics import Scorecard

_JUDGE_TREND_STYLE = {
    "improving": "green",
    "flat": "yellow",
    "declining": "red",
    "insufficient-data": "dim",
}

# The honest caveat — printed VERBATIM as the first line of every report header.
# cheap mode validates the measurement apparatus, not causation.
CAVEAT = (
    "CAVEAT: cheap mode validates that the substrate + metrics correctly register "
    "compounding signals — it is a regression guard for the measurement apparatus, "
    "NOT proof that FlowState causes the LLM to compound. Only --mode real tests "
    "whether FlowState's prefix actually causes the LLM to compound. An axis with "
    "no underlying signal reads as 'insufficient-data' (NOT 'compounding') and "
    "contributes nothing toward a positive verdict."
)

# The real-mode counterpart — printed VERBATIM for --mode real. It deliberately
# contains NO occurrence of the word "cheap" (a regression test asserts this): a
# real run exercises the live substrate, so it DOES test causation.
REAL_CAVEAT = (
    "REAL mode: this run exercised the live substrate, so it tests whether "
    "FlowState's prefix actually causes the LLM to compound — this is a causal "
    "result, not a measurement-apparatus regression guard. An axis with no "
    "underlying signal reads as 'insufficient-data' (NOT 'compounding') and "
    "contributes nothing toward a positive verdict."
)

_module_console = Console()

# Color per axis / verdict label, reusing the verify table palette where sensible.
_VERDICT_STYLE = {
    "compounding": "green",
    "flat": "yellow",
    "regressing": "red",
    "insufficient-data": "dim",
}


def _caveat_for(mode: str) -> str:
    """Mode-selected caveat: the cheap regression-guard wording, or the real note."""
    return REAL_CAVEAT if mode == "real" else CAVEAT


def _mode_note_for(mode: str) -> str:
    """Short, one-line mode note for the JSON payload (no 'cheap' in real mode)."""
    if mode == "real":
        return "real mode tests whether the prefix actually causes the LLM to compound"
    return "cheap mode validates the apparatus, not causation"


def _context_line(
    mode: str,
    arm: str | None,
    sample_size: int | None,
    producers: tuple[str, ...],
) -> str:
    """One-line provenance: mode, arm, sample size (K/trials), producers-present."""
    prods = ", ".join(sorted(producers)) if producers else "none"
    return (
        f"mode={mode} · arm={arm if arm is not None else 'none'} · "
        f"K/trials={sample_size if sample_size is not None else 'n/a'} · "
        f"producers-present={prods}"
    )


def write_json(
    scorecard: Scorecard,
    out_path: Path,
    *,
    judge_results: list[JudgeResult] | None = None,
    mode: str = "cheap",
    arm: str | None = None,
    sample_size: int | None = None,
    producers: tuple[str, ...] = (),
) -> None:
    """Write the scorecard to ``out_path`` as deterministic JSON (sort_keys, indent=2).

    The honest caveat travels WITH the data as a top-level ``caveat`` key, so a
    reader who only sees the archived JSON (a RUNLOG diff, a PR paste) cannot
    mistake the cheap verdict for a causal claim. ``insufficient_data_axes`` lists
    any axis that had no underlying signal, so an inert axis is visible in the
    artifact too.
    """
    payload = {
        "caveat": _caveat_for(mode),
        "mode_note": _mode_note_for(mode),
        "mode": mode,
        "arm": arm,
        "sample_size": sample_size,
        "producers": sorted(producers),
        "axes": {
            "convergence": scorecard.axis_convergence,
            "gotcha_learning": scorecard.axis_gotcha_learning,
            "verify_non_regression": scorecard.axis_verify_non_regression,
            "enrichment": scorecard.axis_enrichment,
        },
        "insufficient_data_axes": _insufficient_axes(scorecard),
        "compounding_score": scorecard.compounding_score,
        "verdict": scorecard.verdict,
        "snapshots": [_snapshot_dict(s) for s in scorecard.snapshots],
    }
    if judge_results:
        summary = summarize(judge_results)
        payload["judge"] = {
            "note": "Tier-2 output-quality judge — EXCLUDED from compounding_score",
            "trend": summary["trend"],
            "first": summary["first"],
            "last": summary["last"],
            "delta": summary["delta"],
            "per_run": [
                {"run_index": r.run_index, "score": r.score, "rationale": r.rationale}
                for r in judge_results
            ],
        }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _insufficient_axes(scorecard: Scorecard) -> list[str]:
    """Names of axes reading 'insufficient-data' (no underlying signal), sorted."""
    named = {
        "convergence": scorecard.axis_convergence,
        "gotcha_learning": scorecard.axis_gotcha_learning,
        "verify_non_regression": scorecard.axis_verify_non_regression,
        "enrichment": scorecard.axis_enrichment,
    }
    return sorted(name for name, state in named.items() if state == "insufficient-data")


def _snapshot_dict(snapshot: object) -> dict:
    """Convert a RunSnapshot to a JSON-safe dict (tuples -> lists)."""
    d = asdict(snapshot)  # type: ignore[call-overload]
    d["layers_present"] = list(d.get("layers_present", ()))
    return d


def _trend_table(
    scorecard: Scorecard,
    *,
    mode: str = "cheap",
    arm: str | None = None,
    sample_size: int | None = None,
) -> Table:
    title = (
        f"bench compounding trend — mode={mode} "
        f"arm={arm if arm is not None else 'none'} "
        f"K/trials={sample_size if sample_size is not None else 'n/a'}"
    )
    table = Table(title=title, border_style="blue")
    table.add_column("Run", style="bold")
    table.add_column("Δartifacts")
    table.add_column("new/re-enc gotchas")
    table.add_column("verify P/F/S")
    table.add_column("prefix tok")
    table.add_column("mem hits")
    table.add_column("layers")
    for s in scorecard.snapshots:
        table.add_row(
            str(s.run_index),
            str(s.artifacts_changed),
            f"{s.new_gotchas}/{s.reencountered_gotchas}",
            f"{s.verify_pass}/{s.verify_fail}/{s.verify_skip}",
            str(s.prefix_tokens),
            str(s.mem_hits),
            str(len(s.layers_present)),
        )
    return table


def _scorecard_panel(scorecard: Scorecard) -> Panel:
    def _styled(label: str) -> str:
        style = _VERDICT_STYLE.get(label, "white")
        return f"[{style}]{label}[/{style}]"

    lines = [
        f"Convergence:           {_styled(scorecard.axis_convergence)}",
        f"Gotcha-learning:       {_styled(scorecard.axis_gotcha_learning)}",
        f"Verify-non-regression: {_styled(scorecard.axis_verify_non_regression)}",
        f"Enrichment:            {_styled(scorecard.axis_enrichment)}",
        "",
        f"CompoundingScore:      [bold]{scorecard.compounding_score}[/bold] (range -4..+4)",
        f"Verdict:               {_styled(scorecard.verdict)}",
    ]
    inert = _insufficient_axes(scorecard)
    if inert:
        lines += [
            "",
            f"[dim]insufficient-data (no signal, excluded from verdict): {', '.join(inert)}[/dim]",
        ]
    return Panel("\n".join(lines), title="Scorecard", border_style="blue")


def _markdown_record(
    scorecard: Scorecard,
    *,
    mode: str = "cheap",
    arm: str | None = None,
    sample_size: int | None = None,
    producers: tuple[str, ...] = (),
) -> str:
    """A RUNLOG-style markdown record of the run."""
    lines = [
        "## Compounding Eval Run",
        "",
        f"> {_caveat_for(mode)}",
        "",
        f"- {_context_line(mode, arm, sample_size, producers)}",
        "",
        "| Run | Δartifacts | new/re-enc | P/F/S | prefix tok | mem hits | layers |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in scorecard.snapshots:
        lines.append(
            f"| {s.run_index} | {s.artifacts_changed} | "
            f"{s.new_gotchas}/{s.reencountered_gotchas} | "
            f"{s.verify_pass}/{s.verify_fail}/{s.verify_skip} | "
            f"{s.prefix_tokens} | {s.mem_hits} | {len(s.layers_present)} |"
        )
    lines += [
        "",
        f"- CompoundingScore: **{scorecard.compounding_score}**",
        f"- Verdict: **{scorecard.verdict}**",
        "",
    ]
    return "\n".join(lines)


def render_report(
    scorecard: Scorecard,
    *,
    console: Console | None = None,
    markdown: bool = False,
    mode: str = "cheap",
    arm: str | None = None,
    sample_size: int | None = None,
    producers: tuple[str, ...] = (),
) -> None:
    """Print the caveat header, the trend table, and the scorecard panel.

    The mode-selected caveat is ALWAYS printed first, followed by a one-line
    provenance header (mode / arm / K / producers-present). When ``markdown`` is
    True, a RUNLOG-style markdown record is also emitted after the Rich output.
    """
    con = console or _module_console
    con.print(Panel(_caveat_for(mode), title="Honest Caveat", border_style="yellow"))
    con.print(_context_line(mode, arm, sample_size, producers))
    con.print(_trend_table(scorecard, mode=mode, arm=arm, sample_size=sample_size))
    con.print(_scorecard_panel(scorecard))
    if markdown:
        con.print(
            _markdown_record(
                scorecard, mode=mode, arm=arm, sample_size=sample_size, producers=producers
            )
        )


def render_judge_panel(results: list[JudgeResult], *, console: Console | None = None) -> None:
    """Render the Tier-2 output-quality panel — SEPARATE from the mechanical scorecard.

    A rising score across runs is evidence the accumulated context improved output
    quality. This is advisory and NEVER feeds the CompoundingScore.
    """
    con = console or _module_console
    summary = summarize(results)
    trend = summary["trend"]
    style = _JUDGE_TREND_STYLE.get(trend, "white")
    lines = [
        "Tier-2 LLM-as-judge — does the accumulating context make OUTPUT better?",
        "(advisory; EXCLUDED from the mechanical CompoundingScore)",
        "",
    ]
    for r in results:
        score = "—" if r.score is None else f"{r.score:g}/10"
        lines.append(f"run {r.run_index}: [bold]{score}[/bold]  [dim]{r.rationale}[/dim]")
    lines += [
        "",
        f"Quality trend: [{style}]{trend}[/{style}]"
        + (f"  (Δ {summary['delta']:+g})" if summary["delta"] is not None else ""),
    ]
    con.print(Panel("\n".join(lines), title="Output Quality (Tier-2)", border_style="magenta"))
