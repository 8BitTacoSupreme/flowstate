"""Tests for bench/prepare_fixture.py — the single per-arm fixture-preparation entry point.

Covers:
- wiki producer success (memory.db populated) and failure (empty memory.db).
- pack producer wiring via flowstate.pack.run_pack (monkeypatched failure path).
- default --arms provisions both producers; overall return code reflects any failure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import bench.distiller as distiller_mod
import bench.prepare_fixture as prepare_fixture_mod
from bench.distiller import _WIKI_CORPUS_REL
from bench.prepare_fixture import main
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.pack import PackResult


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


def test_wiki_arm_with_memory_builds_corpus_and_returns_0(tmp_path):
    """--arms wiki on a root with a populated memory.db builds the corpus, returns 0."""
    _seed(tmp_path, [MemoryKind.DECISION, MemoryKind.INSIGHT])

    rc = main(["--root", str(tmp_path), "--arms", "wiki"])

    assert rc == 0
    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    assert len(list(corpus_dir.glob("**/*.md"))) >= 2


def test_wiki_arm_empty_memory_returns_nonzero_and_reports_failure(tmp_path, capsys):
    """--arms wiki on a root with an empty memory.db -> non-zero, wiki reported failed."""
    rc = main(["--root", str(tmp_path), "--arms", "wiki"])

    assert rc != 0
    captured = capsys.readouterr()
    assert "wiki" in (captured.out + captured.err)
    assert "failed" in (captured.out + captured.err)


def test_pack_producer_invoked_via_run_pack_monkeypatched_failure(tmp_path, monkeypatch, capsys):
    """The pack producer is invoked via run_pack; a failure is reported and non-zero returned."""
    stub = Mock(return_value=PackResult(success=False, error="repomix CLI not found"))
    monkeypatch.setattr(prepare_fixture_mod, "run_pack", stub)

    rc = main(["--root", str(tmp_path), "--arms", "pack"])

    assert rc != 0
    stub.assert_called_once()
    captured = capsys.readouterr()
    assert "pack" in (captured.out + captured.err)
    assert "failed" in (captured.out + captured.err)


def test_default_arms_builds_both_producers_all_success_returns_0(tmp_path, monkeypatch):
    """Default --arms (no flag) invokes BOTH producers; an all-success run returns 0."""
    pack_stub = Mock(return_value=PackResult(success=True, output_path=tmp_path / "pack.xml"))
    monkeypatch.setattr(prepare_fixture_mod, "run_pack", pack_stub)
    distiller_stub = Mock(return_value=0)
    monkeypatch.setattr(distiller_mod, "main", distiller_stub)
    monkeypatch.setattr(prepare_fixture_mod.distiller, "main", distiller_stub)

    rc = main(["--root", str(tmp_path)])

    assert rc == 0
    pack_stub.assert_called_once()
    distiller_stub.assert_called_once()
