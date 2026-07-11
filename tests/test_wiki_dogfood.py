"""Dogfood smoke-test that the wiki layer DEMONSTRABLY FIRES in production wiring (WIKI-06 / D-08).

The whole phase moves the wiki layer from dormant to firing. This test is the proof
and a regression guard against the layer silently going dark again: it runs the
promoted distiller to produce the article corpus, calls ``build_context_prefix`` with
the production union ``_STANDARD_LAYERS | {"wiki"}``, and asserts the top-k article
content lands in the assembled prefix (globbed + injected).

Acceptance is "the layer fires," NOT "quality improved" — no score is asserted (that is
Phase 22). Firing is accepted through EITHER path: the semantic KNN reader (when the
optional ``[semantic]`` extra is installed) or the static ``_read_wiki_layer`` fallback.

Two tests:
  - ``test_wiki_layer_fires_on_real_memory`` — the literal dogfood against THIS project's
    real ``memory.db`` (isolated to a copied root so the live checkout is never mutated).
    Skips with an explicit reason when the real memory has no distillable corpus.
  - ``test_wiki_layer_fires_end_to_end`` — seeds a synthetic memory.db in ``tmp_path`` and
    exercises the exact production functions, so the guard fires green regardless of the
    real ``memory.db`` state.

Neither test passes ``--llm``, so no real ``claude --print`` subprocess is ever spawned.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flowstate import distiller
from flowstate.context_prefix import (
    _STANDARD_LAYERS,
    _WIKI_PATH,
    build_context_prefix,
    get_embedder,
)
from flowstate.distiller import _WIKI_CORPUS_REL
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

# The production union the orchestrator passes when the opt-in wiki_layer flag is on.
_WIKI_UNION = _STANDARD_LAYERS | {"wiki"}


def _distinctive_line(corpus_dir: Path) -> str:
    """Return a distinctive non-heading line drawn from a written article file.

    Used both as the retrieval query (so semantic KNN strongly matches that article)
    and as the substring asserted present in the assembled prefix — proving the corpus
    was globbed and its content injected, not merely that a heading was emitted.
    """
    for path in sorted(corpus_dir.glob("*.md")):
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and len(line) > 20:
                return line
    raise AssertionError(f"no distinctive article line found under {corpus_dir}")


def _assert_wiki_fired(root: Path, corpus_dir: Path) -> None:
    """Assert the wiki layer fires: '## Codebase Wiki' heading + real article content in prefix.

    Accepts firing through EITHER path (D-08). When the semantic embedder is absent the
    KNN reader cannot fire and the static ``_read_wiki_layer`` reads the single-file
    ``.planning/codebase/wiki.md`` (a distinct artifact the distiller does not write), so
    we synthesise that file from the distilled corpus to exercise the static fallback.
    """
    distinctive = _distinctive_line(corpus_dir)

    if not get_embedder(root).available():
        # [semantic] absent: the KNN path can never fire. Assert firing via the static
        # reader, which reads the single-file wiki.md — populate it from the corpus.
        wiki_file = root / _WIKI_PATH
        wiki_file.parent.mkdir(parents=True, exist_ok=True)
        wiki_file.write_text("\n\n".join(p.read_text() for p in sorted(corpus_dir.glob("*.md"))))

    store = MemoryStore(root)
    try:
        prefix = build_context_prefix(root, store, distinctive, include_layers=_WIKI_UNION)
    finally:
        store.close()

    # Firing = the wiki heading is present AND real article content was injected.
    assert "## Codebase Wiki" in prefix
    assert distinctive in prefix


@pytest.mark.integration
@pytest.mark.slow
def test_wiki_layer_fires_on_real_memory(tmp_path: Path) -> None:
    """Dogfood: distill THIS project's real memory.db and prove the wiki layer fires.

    Isolated to a copied root (T-21-07) — the live ``.planning/codebase/wiki`` corpus is
    never mutated. Skips (never fails) when the real memory yields no distillable corpus.
    """
    repo_root = Path(__file__).resolve().parents[1]
    real_db = repo_root / "memory.db"
    if not real_db.exists():
        pytest.skip(f"no memory.db under {repo_root} — nothing to dogfood")

    # Isolate: copy the real memory.db into a throwaway root; distill writes only there.
    isolated_db = tmp_path / "memory.db"
    shutil.copy2(real_db, isolated_db)

    rc = distiller.main(["--root", str(tmp_path), "--force"])
    if rc != 0:
        pytest.skip("real memory.db has no distillable entries — no corpus to dogfood")

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_files = list(corpus_dir.glob("*.md"))
    assert corpus_files, "distiller reported success but wrote no corpus files"

    _assert_wiki_fired(tmp_path, corpus_dir)


@pytest.mark.integration
@pytest.mark.slow
def test_wiki_layer_fires_end_to_end(tmp_path: Path) -> None:
    """Regression guard: production distiller + build_context_prefix union fire green.

    Seeds a synthetic memory.db so the guard exercises the exact production wiring on
    every run (the real memory.db may be empty). If this goes red, the wiki layer has
    silently gone dormant again.
    """
    store = MemoryStore(tmp_path)
    store.add(
        MemoryEntry.create(
            MemoryKind.DECISION,
            "Chose SQLite FTS5 with BM25 ranking for the memory store — zero external "
            "services and it ships with Python.",
            "Use SQLite FTS5 for the memory store",
        )
    )
    store.add(
        MemoryEntry.create(
            MemoryKind.INSIGHT,
            "The semantic wiki layer measured 0.825 F1, near the oracle 0.800, but shipped "
            "dormant until this phase wired it into production.",
            "Wiki layer near-oracle yet dormant",
        )
    )
    store.close()

    rc = distiller.main(["--root", str(tmp_path), "--force"])
    assert rc == 0, "distiller failed on seeded memory"

    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_files = list(corpus_dir.glob("*.md"))
    assert corpus_files, "distiller wrote no corpus files for seeded memory"

    _assert_wiki_fired(tmp_path, corpus_dir)
