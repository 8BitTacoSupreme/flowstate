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

from bench.metrics import Scorecard

# The honest caveat — printed VERBATIM as the first line of every report header.
# cheap mode validates the measurement apparatus, not causation.
CAVEAT = (
    "CAVEAT: cheap mode validates that the substrate + metrics correctly register "
    "compounding signals — it is a regression guard for the measurement apparatus, "
    "NOT proof that FlowState causes the LLM to compound. Only --mode real tests "
    "whether FlowState's prefix actually causes the LLM to compound."
)

_module_console = Console()

# Color per axis / verdict label, reusing the verify table palette where sensible.
_VERDICT_STYLE = {
    "compounding": "green",
    "flat": "yellow",
    "regressing": "red",
}


def write_json(scorecard: Scorecard, out_path: Path) -> None:
    """Write the scorecard to ``out_path`` as deterministic JSON (sort_keys, indent=2)."""
    payload = {
        "axes": {
            "convergence": scorecard.axis_convergence,
            "gotcha_learning": scorecard.axis_gotcha_learning,
            "verify_non_regression": scorecard.axis_verify_non_regression,
            "enrichment": scorecard.axis_enrichment,
        },
        "compounding_score": scorecard.compounding_score,
        "verdict": scorecard.verdict,
        "snapshots": [_snapshot_dict(s) for s in scorecard.snapshots],
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def _snapshot_dict(snapshot: object) -> dict:
    """Convert a RunSnapshot to a JSON-safe dict (tuples -> lists)."""
    d = asdict(snapshot)  # type: ignore[call-overload]
    d["layers_present"] = list(d.get("layers_present", ()))
    return d


def _trend_table(scorecard: Scorecard) -> Table:
    table = Table(title="bench compounding trend", border_style="blue")
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

    body = "\n".join(
        [
            f"Convergence:           {_styled(scorecard.axis_convergence)}",
            f"Gotcha-learning:       {_styled(scorecard.axis_gotcha_learning)}",
            f"Verify-non-regression: {_styled(scorecard.axis_verify_non_regression)}",
            f"Enrichment:            {_styled(scorecard.axis_enrichment)}",
            "",
            f"CompoundingScore:      [bold]{scorecard.compounding_score}[/bold] (range -4..+4)",
            f"Verdict:               {_styled(scorecard.verdict)}",
        ]
    )
    return Panel(body, title="Scorecard", border_style="blue")


def _markdown_record(scorecard: Scorecard) -> str:
    """A RUNLOG-style markdown record of the run."""
    lines = [
        "## Compounding Eval Run",
        "",
        f"> {CAVEAT}",
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
) -> None:
    """Print the caveat header, the trend table, and the scorecard panel.

    The caveat is ALWAYS printed first. When ``markdown`` is True, a RUNLOG-style
    markdown record is also emitted after the Rich output.
    """
    con = console or _module_console
    con.print(Panel(CAVEAT, title="Honest Caveat", border_style="yellow"))
    con.print(_trend_table(scorecard))
    con.print(_scorecard_panel(scorecard))
    if markdown:
        con.print(_markdown_record(scorecard))
