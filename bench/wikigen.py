"""One-time distilled-CAG architecture wiki generator.

Reads the repomix pack from .planning/codebase/repomix-pack.xml, sends it to
the claude CLI with a single architecture-wiki prompt, and writes the output to
.planning/codebase/wiki.md.

This is a research/bench tooling module — NOT a flowstate CLI subcommand.
Invoke via: python -m bench.wikigen --root <project-root>

The produced wiki.md is durable LLM context for the wiki arm of the compounding
bench (include_layers={'fixtures','wiki'} in build_context_prefix).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from bench.judge import _locate_claude

_PACK_REL = ".planning/codebase/repomix-pack.xml"
_WIKI_REL = ".planning/codebase/wiki.md"
_MAX_PACK_CHARS = 120_000
_WIKIGEN_TIMEOUT = 600

PROMPT_HEADER = (
    "Produce a dense, high-signal architecture wiki for this codebase, "
    "to be used as durable LLM context (not prose for humans). "
    "Sections: (1) one-paragraph system overview; "
    "(2) module/architecture map — per module: responsibility, key files "
    "(paths), key public functions/classes; "
    "(3) control/data flow; "
    "(4) key abstractions & invariants; "
    "(5) gotchas/constraints. "
    "Use concrete names and paths from the code. No filler. "
    "Markdown. Target ~3000-6000 tokens.\n\nCODEBASE PACK:\n\n"
)


def main(argv: list[str] | None = None) -> int:
    """Generate a distilled-CAG wiki.md from the repomix pack. Never raises."""
    ap = argparse.ArgumentParser(
        prog="bench.wikigen",
        description="Generate .planning/codebase/wiki.md from the repomix pack via one claude call.",
    )
    ap.add_argument("--root", type=Path, required=True, help="Project root directory.")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing wiki.md without prompting.",
    )
    ap.add_argument(
        "--model",
        default="opus",
        help="Model to use for the claude CLI call (default: opus).",
    )
    args = ap.parse_args(argv)

    root = args.root
    pack_path = root / _PACK_REL
    wiki_path = root / _WIKI_REL

    # 1. Check pack exists
    if not pack_path.exists():
        print(
            f"wikigen: pack file not found at {pack_path}; "
            "run `flowstate pack` or `python -m bench.repomix` to generate it first.",
            file=sys.stderr,
        )
        return 1

    # 2. Skip if wiki already exists and --force not set
    if wiki_path.exists() and not args.force:
        print("wiki up to date; skipping (use --force to regenerate)")
        return 0

    # 3. Locate claude
    claude = _locate_claude()
    if not claude:
        print(
            "wikigen: claude CLI not found; set FLOWSTATE_CLAUDE_BIN or add claude to PATH.",
            file=sys.stderr,
        )
        return 1

    # 4. Read and truncate pack
    try:
        pack_text = pack_path.read_text()
    except Exception as exc:
        print(f"wikigen: could not read pack file {pack_path}: {exc}", file=sys.stderr)
        return 1
    pack_text = pack_text[:_MAX_PACK_CHARS]
    prompt = PROMPT_HEADER + pack_text

    # 5. Run claude
    cmd = [claude, "--print", "--max-turns", "1", "--model", args.model, "--", prompt]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_WIKIGEN_TIMEOUT)
    except Exception as exc:
        print(f"wikigen: claude subprocess failed: {exc}", file=sys.stderr)
        return 1

    if proc.returncode == 0 and proc.stdout.strip():
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text(proc.stdout)
        print(wiki_path)
        return 0
    else:
        reason = f"returncode={proc.returncode}" if proc.returncode != 0 else "(empty output)"
        print(f"wikigen: claude call failed ({reason})", file=sys.stderr)
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
