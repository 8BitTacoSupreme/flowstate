"""Memory-to-wiki distiller — the article-corpus producer for the wiki bench arm.

Reads the accumulated ``memory.db`` (via ``flowstate.memory.MemoryStore``) and
writes an ARTICLE CORPUS — multiple ``*.md`` files, one per non-empty
``MemoryKind`` — under ``.planning/codebase/wiki/``. This is exactly the
directory the Phase-11 semantic wiki reader globs
(``flowstate.context_prefix._semantic_wiki_layer``, ``_WIKI_CORPUS_DIR``).

This closes the HAR-03b generator/reader mismatch: ``bench/wikigen.py`` writes
a SINGLE FILE (``wiki.md``) that the corpus-globbing reader never looks at.
The reader contract (corpus-of-articles) is unchanged — this module fixes the
producer side.

This is a research/bench tooling module — NOT a flowstate CLI subcommand.
Invoke via: python -m bench.distiller --root <project-root>

Default output is deterministic (no LLM, no subprocess). ``--llm`` optionally
densifies each article via one bounded ``claude --print`` call per article,
degrading to the deterministic text on any failure.
"""

from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys
from pathlib import Path

from bench.judge import _locate_claude
from flowstate.memory import MemoryKind, MemoryStore

_WIKI_CORPUS_REL = ".planning/codebase/wiki"  # matches context_prefix._WIKI_CORPUS_DIR
_DISTILL_TIMEOUT = 300

# Kinds worth distilling into durable wiki knowledge, in deterministic article order.
# TOOL_RUN is excluded — it is ephemeral run-log noise, not durable knowledge.
_ARTICLE_KINDS: list[MemoryKind] = [
    MemoryKind.DECISION,
    MemoryKind.INSIGHT,
    MemoryKind.RESEARCH,
    MemoryKind.STRATEGY,
    MemoryKind.RUN,
]

PROMPT_HEADER = (
    "Densify the following memory-derived article into dense, high-signal, "
    "durable LLM context (not prose for humans). Keep it knowledge, not code. "
    "Preserve concrete names, decisions, and facts already present. "
    "Markdown. No filler.\n\nARTICLE:\n\n"
)


def _article_filename(index: int, kind: MemoryKind) -> str:
    """Deterministic numeric+kind filename, e.g. '01-decisions.md'."""
    return f"{index:02d}-{kind.value}s.md"


def _render_article(kind: MemoryKind, entries: list) -> str:
    """Render one article: '# {Kind title}' heading + one '## {summary}' block per entry."""
    lines = [f"# {kind.value.title()}", ""]
    for entry in entries:
        lines.append(f"## {entry.summary}")
        lines.append("")
        lines.append(entry.content)
        lines.append("")
    return "\n".join(lines)


def _densify(article_text: str, claude: str, model: str) -> str:
    """Run one bounded claude densification pass. Returns original text on any failure."""
    cmd = [
        claude,
        "--print",
        "--max-turns",
        "1",
        "--model",
        model,
        "--",
        PROMPT_HEADER + article_text,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_DISTILL_TIMEOUT)
    except Exception:
        return article_text
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout
    return article_text


def main(argv: list[str] | None = None) -> int:
    """Distill memory.db into the wiki article corpus. Never raises."""
    ap = argparse.ArgumentParser(
        prog="bench.distiller",
        description=(
            "Generate the .planning/codebase/wiki/ article corpus from memory.db "
            "(the corpus the Phase-11 semantic wiki reader globs)."
        ),
    )
    ap.add_argument("--root", type=Path, required=True, help="Project root directory.")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing populated corpus without prompting.",
    )
    ap.add_argument(
        "--model",
        default="opus",
        help="Model to use for --llm densification calls (default: opus).",
    )
    ap.add_argument(
        "--llm",
        action="store_true",
        help="Densify each article via one bounded claude call (default: deterministic only).",
    )
    args = ap.parse_args(argv)

    root = args.root
    corpus_dir = root / _WIKI_CORPUS_REL

    # 1. Skip if corpus already populated and --force not set.
    if corpus_dir.is_dir() and any(corpus_dir.glob("**/*.md")) and not args.force:
        print("wiki corpus up to date; skipping (use --force to regenerate)")
        return 0

    # 2. Read memory, grouped by kind. Never let store errors propagate.
    store = None
    try:
        store = MemoryStore(root)
        by_kind = {kind: store.get_by_kind(kind) for kind in _ARTICLE_KINDS}
    except Exception as exc:
        print(f"distiller: could not read memory.db under {root}: {exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            with contextlib.suppress(Exception):
                store.close()

    non_empty = {kind: entries for kind, entries in by_kind.items() if entries}

    # 3. Fail loud on empty memory — never write a partial/empty corpus.
    if not non_empty:
        print(
            f"distiller: memory.db under {root} has no distillable entries "
            f"(kinds checked: {[k.value for k in _ARTICLE_KINDS]}); writing no corpus.",
            file=sys.stderr,
        )
        return 1

    # 4. Locate claude if --llm requested.
    claude = None
    if args.llm:
        claude = _locate_claude()
        if claude is None:
            print(
                "distiller: --llm requested but claude CLI not found; "
                "writing deterministic articles unchanged.",
                file=sys.stderr,
            )

    # 5. Render (+ optionally densify) each article. Build in-memory first so a
    #    mid-loop failure never leaves a half-written corpus on disk.
    written: dict[str, str] = {}
    for index, (kind, entries) in enumerate(non_empty.items(), start=1):
        article = _render_article(kind, entries)
        if args.llm and claude is not None:
            article = _densify(article, claude, args.model)
        written[_article_filename(index, kind)] = article

    corpus_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in written.items():
        (corpus_dir / filename).write_text(text)

    print(f"wrote {len(written)} article(s) to {corpus_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
