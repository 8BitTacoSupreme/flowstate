"""Tests for flowstate/distiller.py — the promoted memory-to-wiki distiller.

Task 1 (core, against the production import path): corpus shape + empty-memory
guard. The exhaustive --llm/force/WR-01/WR-04 coverage lives in
tests/test_bench_distiller.py against the re-export shim; these tests lock the
production module's public surface. Task 2 appends is_wiki_stale coverage.
"""

from __future__ import annotations

from pathlib import Path

from flowstate.distiller import _WIKI_CORPUS_REL, main
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore


def _seed(root: Path, kinds: list[MemoryKind]) -> None:
    """Seed a memory.db under root with one entry per requested kind."""
    with MemoryStore(root) as store:
        for kind in kinds:
            store.add(
                MemoryEntry.create(
                    kind,
                    content=f"content for {kind.value}",
                    summary=f"{kind.value} summary",
                )
            )


def test_imports_from_production_path():
    """The distiller logic is importable directly from flowstate (no bench needed)."""
    assert callable(main)
    assert _WIKI_CORPUS_REL == ".planning/codebase/wiki"


def test_two_kinds_produce_two_articles(tmp_path):
    """A memory.db with two kinds -> two headed *.md articles, rc 0."""
    _seed(tmp_path, [MemoryKind.DECISION, MemoryKind.INSIGHT])

    rc = main(["--root", str(tmp_path)])
    assert rc == 0

    articles = sorted((tmp_path / _WIKI_CORPUS_REL).glob("**/*.md"))
    assert len(articles) == 2
    for article in articles:
        assert article.read_text().startswith("# ")


def test_empty_memory_returns_nonzero_no_files(tmp_path):
    """Empty/absent memory.db -> non-zero exit, no *.md files written (fail-loud)."""
    rc = main(["--root", str(tmp_path)])
    assert rc != 0

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    assert not corpus_dir.exists() or not list(corpus_dir.glob("**/*.md"))
