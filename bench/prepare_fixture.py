"""Fixture-preparation entry point — provisions every arm's producer before the matrix runs.

This is the ONE `prepare-fixture` path (HAR-03, success criterion 3): a single
command that generates what each `--layers` arm needs before
`bench.compound_eval`'s HAR-02 fail-loud gate (`_missing_producer`) runs. It wires
the existing producers — it does not reimplement either:

  pack -> flowstate.pack.run_pack(root)          (repomix pack)
  wiki -> bench.distiller.main(["--root", ...])  (wiki article corpus)

This is a research/bench tooling module — NOT a flowstate CLI subcommand.
Invoke via: python -m bench.prepare_fixture --root <project-root>

Each producer's outcome is reported on one line; the overall return code is
non-zero if ANY requested producer failed (fail loud, no silent skip). A
producer exception is caught and reported as a failure for that producer —
this module never raises.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

import bench.distiller as distiller
from flowstate.pack import run_pack

_console = Console()

# Arms that have a real producer to invoke. Arms without one (full/memory/none)
# are accepted but are a no-op — they always succeed.
_PRODUCER_ARMS = ("pack", "wiki")


def _parse_arms(raw: list[str] | None) -> list[str]:
    """Flatten repeatable/comma-list --arms values; default provisions pack+wiki."""
    if not raw:
        return list(_PRODUCER_ARMS)
    arms: list[str] = []
    for item in raw:
        arms.extend(a.strip() for a in item.split(",") if a.strip())
    return arms


def _run_pack_producer(root: Path) -> tuple[bool, str]:
    """Invoke the pack producer. Returns (success, detail-message). Never raises."""
    try:
        result = run_pack(root)
    except Exception as exc:  # never raise — a producer failure is reported, not fatal
        return False, str(exc)
    if result.success:
        return True, f"built {result.output_path}"
    return False, result.error or "run_pack failed with no error message"


def _run_wiki_producer(root: Path, *, force: bool, llm: bool, model: str) -> tuple[bool, str]:
    """Invoke the wiki producer (the distiller). Returns (success, detail-message). Never raises."""
    argv = ["--root", str(root)]
    if force:
        argv.append("--force")
    if llm:
        argv.extend(["--llm", "--model", model])
    try:
        rc = distiller.main(argv)
    except Exception as exc:  # never raise — a producer failure is reported, not fatal
        return False, str(exc)
    if rc == 0:
        return True, "wiki corpus built"
    return False, f"distiller exited with code {rc}"


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="bench.prepare_fixture",
        description=(
            "Provision every arm's producer artifact (repomix pack, wiki article "
            "corpus) before the bench.compound_eval arm matrix runs."
        ),
    )
    ap.add_argument("--root", type=Path, required=True, help="Project root directory.")
    ap.add_argument(
        "--arms",
        action="append",
        default=None,
        help=(
            "Comma-separated or repeatable list of arms to provision "
            "(default: pack,wiki). Arms without a producer (full/memory/none) "
            "are accepted as a no-op."
        ),
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Force-regenerate the wiki producer's corpus (passed through to the distiller).",
    )
    ap.add_argument(
        "--llm",
        action="store_true",
        help="Enable LLM densification for the wiki producer (default: off).",
    )
    ap.add_argument(
        "--model",
        default="opus",
        help="Model for --llm wiki densification (default: opus).",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    """Provision each requested arm's producer. Never raises. Returns 0 iff all succeed."""
    args = _build_parser().parse_args(argv)
    root = args.root
    arms = _parse_arms(args.arms)

    failed: list[str] = []
    for arm in arms:
        if arm == "pack":
            ok, detail = _run_pack_producer(root)
        elif arm == "wiki":
            ok, detail = _run_wiki_producer(root, force=args.force, llm=args.llm, model=args.model)
        else:
            _console.print(f"[dim]{arm}: no producer required; skipping.[/dim]")
            continue

        if ok:
            _console.print(f"[green]{arm}: built[/green] — {detail}")
        else:
            _console.print(f"[red]{arm}: failed[/red] — {detail}")
            failed.append(arm)

    if failed:
        _console.print(
            f"[bold red]prepare-fixture: {len(failed)} producer(s) failed: "
            f"{', '.join(failed)}[/bold red]"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
