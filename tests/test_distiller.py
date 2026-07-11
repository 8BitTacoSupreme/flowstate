"""Tests for flowstate/distiller.py — the promoted memory-to-wiki distiller.

Task 1 (core, against the production import path): corpus shape + empty-memory
guard. The exhaustive --llm/force/WR-01/WR-04 coverage lives in
tests/test_bench_distiller.py against the re-export shim; these tests lock the
production module's public surface. Task 2 appends is_wiki_stale coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from flowstate.distiller import _WIKI_CORPUS_REL, is_wiki_stale, main
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import FlowStateModel, InstallEntry


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


# ---------------------------------------------------------------------------
# Task 2: is_wiki_stale — manifest-tracked staleness gate (mirrors is_pack_stale)
# ---------------------------------------------------------------------------


def _state_with_wiki_entry(created_at: datetime) -> FlowStateModel:
    state = FlowStateModel()
    state.install_manifest.append(
        InstallEntry(
            path=_WIKI_CORPUS_REL,
            owner="distill",
            kind="wiki",
            created_at=created_at,
        )
    )
    return state


def test_wiki_manifest_entry_on_directory_path_is_valid():
    """A kind='wiki' entry on the corpus DIRECTORY constructs (checksum skipped)."""
    entry = InstallEntry(path=_WIKI_CORPUS_REL, owner="distill", kind="wiki")
    assert entry.kind == "wiki"


def test_is_wiki_stale_absent_entry_is_stale(tmp_path):
    """No manifest entry -> stale (needs first generation)."""
    assert is_wiki_stale(tmp_path, FlowStateModel()) is True


def test_is_wiki_stale_entry_newer_than_memory_not_stale(tmp_path):
    """Entry created_at newer than memory.db mtime -> not stale."""
    _seed(tmp_path, [MemoryKind.DECISION])
    state = _state_with_wiki_entry(datetime.now(UTC) + timedelta(hours=1))
    assert is_wiki_stale(tmp_path, state) is False


def test_is_wiki_stale_memory_touched_after_entry_is_stale(tmp_path):
    """memory.db mtime newer than the entry created_at -> stale."""
    _seed(tmp_path, [MemoryKind.DECISION])
    state = _state_with_wiki_entry(datetime.now(UTC) - timedelta(hours=1))
    assert is_wiki_stale(tmp_path, state) is True


def test_is_wiki_stale_absent_memory_db_not_stale(tmp_path):
    """Entry present but no memory.db on disk -> not stale (nothing to regenerate from)."""
    state = _state_with_wiki_entry(datetime.now(UTC))
    assert is_wiki_stale(tmp_path, state) is False


def test_register_wiki_directory_path_does_not_raise(tmp_path):
    """_register with kind='wiki' on a directory path skips the checksum and does not raise."""
    from flowstate.context import _register

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_dir.mkdir(parents=True)
    state = FlowStateModel()
    _register(state, tmp_path, corpus_dir, owner="distill", kind="wiki")

    entry = next(e for e in state.install_manifest if e.path == _WIKI_CORPUS_REL)
    assert entry.kind == "wiki"
    assert entry.checksum is None
