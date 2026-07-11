"""Tests for bench/distiller.py — memory-to-wiki article-corpus distiller.

Covers:
- Task 1 (deterministic core): corpus shape, empty-memory guard, force/skip guard.
"""

from __future__ import annotations

from pathlib import Path

from bench.distiller import _WIKI_CORPUS_REL, main

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


def test_two_kinds_produce_two_articles(tmp_path):
    """A memory.db with >=2 kinds -> distiller writes >=2 *.md files, each headed."""
    _seed(tmp_path, [MemoryKind.DECISION, MemoryKind.INSIGHT])

    rc = main(["--root", str(tmp_path)])
    assert rc == 0

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    articles = sorted(corpus_dir.glob("**/*.md"))
    assert len(articles) >= 2
    for article in articles:
        text = article.read_text()
        assert text.strip()
        assert text.startswith("# ")


def test_empty_memory_returns_nonzero_no_files(tmp_path):
    """Empty/absent memory.db -> non-zero exit, no *.md files written."""
    rc = main(["--root", str(tmp_path)])
    assert rc != 0

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    assert not list(corpus_dir.glob("**/*.md")) if corpus_dir.exists() else True


def test_populated_corpus_without_force_skips(tmp_path):
    """Existing populated corpus without --force -> returns 0, does not overwrite."""
    _seed(tmp_path, [MemoryKind.DECISION, MemoryKind.INSIGHT])
    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_dir.mkdir(parents=True)
    existing = corpus_dir / "01-decisions.md"
    existing.write_text("preexisting content")
    before_mtime = existing.stat().st_mtime

    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    assert existing.read_text() == "preexisting content"
    assert existing.stat().st_mtime == before_mtime


def test_populated_corpus_with_force_rewrites(tmp_path):
    """Existing populated corpus with --force -> rewrites from current memory."""
    _seed(tmp_path, [MemoryKind.DECISION, MemoryKind.INSIGHT])
    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_dir.mkdir(parents=True)
    existing = corpus_dir / "01-decisions.md"
    existing.write_text("stale content")

    rc = main(["--root", str(tmp_path), "--force"])
    assert rc == 0
    assert existing.read_text() != "stale content"


def test_glob_matches_reader_contract(tmp_path):
    """Written files are real .md files directly under the corpus dir the reader globs."""
    _seed(tmp_path, [MemoryKind.RESEARCH, MemoryKind.STRATEGY, MemoryKind.RUN])

    rc = main(["--root", str(tmp_path)])
    assert rc == 0

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    matched = sorted(corpus_dir.glob("**/*.md"))
    assert len(matched) == 3
