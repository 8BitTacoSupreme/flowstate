"""Memory-to-wiki distiller — the article-corpus producer for the wiki layer.

Reads the accumulated ``memory.db`` (via ``flowstate.memory.MemoryStore``) and
writes an ARTICLE CORPUS — multiple ``*.md`` files, one per non-empty
``MemoryKind`` — under ``.planning/codebase/wiki/``. This is exactly the
directory the Phase-11 semantic wiki reader globs
(``flowstate.context_prefix._semantic_wiki_layer``, ``_WIKI_CORPUS_DIR``).

Promoted from ``bench/distiller.py`` to a production module (D-01). ``bench/``
re-imports from here so the bench arm keeps working with no logic duplication.
This module imports NOTHING from ``bench/`` — the wheel ships only
``packages=["flowstate"]``, so ``flowstate distill`` must resolve on an installed
(non-repo) environment.

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

from flowstate.bridge import _find_claude
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


def _locate_claude() -> str | None:
    """Locate the claude CLI binary, or None when absent.

    Delegates to ``flowstate.bridge._find_claude`` (the production locator),
    mapping its ``""``-on-absent return to ``None`` so the ``--llm`` densify
    path's ``if claude is None:`` contract is preserved.
    """
    found = _find_claude()
    return found or None


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


def is_wiki_stale(root: Path, state) -> bool:
    """Return True if the wiki corpus is absent or memory.db is newer than it.

    Mirrors ``flowstate.pack.is_pack_stale`` (D-04), but keys on ``memory.db``
    mtime as the staleness source instead of the newest ``*.py`` source file.

    Args:
        root: Project root directory.
        state: FlowStateModel — consulted for the wiki's install_manifest entry.

    Returns:
        True  — corpus needs regeneration (no manifest entry, or memory.db newer).
        False — corpus is current (entry present and memory.db absent or older).
    """
    entry = next((e for e in state.install_manifest if e.path == _WIKI_CORPUS_REL), None)
    if entry is None:
        return True

    # A manifest entry can outlive the corpus it describes: .planning/codebase/
    # is a frequently-cleaned tree, so the wiki directory (or its articles) can
    # be deleted while memory.db is untouched. Treat "corpus gone" as stale so a
    # --force distill run actually regenerates it — unlike is_pack_stale, this is
    # a DIRECTORY corpus where any subset of *.md articles can go missing (WR-01).
    corpus_dir = root / _WIKI_CORPUS_REL
    if not corpus_dir.is_dir() or not any(corpus_dir.glob("**/*.md")):
        return True

    memory_db = root / "memory.db"
    if not memory_db.exists():
        return False

    return memory_db.stat().st_mtime > entry.created_at.timestamp()


def main(argv: list[str] | None = None) -> int:
    """Distill memory.db into the wiki article corpus. Never raises."""
    ap = argparse.ArgumentParser(
        prog="flowstate.distiller",
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
        # Pass an explicit high limit so distillation is complete, not a
        # head-slice: get_by_kind defaults to limit=20, which would silently
        # drop the oldest knowledge from any kind with >20 entries and turn the
        # durable wiki corpus into a rolling 20-item window (WR-01).
        by_kind = {kind: store.get_by_kind(kind, limit=100_000) for kind in _ARTICLE_KINDS}
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

    # Honor the "Never raises" contract on the standalone __main__ path: a
    # read-only FS / permission error / non-dir at corpus_dir must be reported,
    # not propagated as a traceback (WR-04).
    try:
        corpus_dir.mkdir(parents=True, exist_ok=True)
        for filename, text in written.items():
            (corpus_dir / filename).write_text(text)
    except OSError as exc:
        print(f"distiller: could not write corpus under {corpus_dir}: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {len(written)} article(s) to {corpus_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
