"""Tests for flowstate/distiller.py — the promoted memory-to-wiki distiller.

Task 1 (core, against the production import path): corpus shape + empty-memory
guard. The exhaustive --llm/force/WR-01/WR-04 coverage lives in
tests/test_bench_distiller.py against the re-export shim; these tests lock the
production module's public surface. Task 2 appends is_wiki_stale coverage.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from flowstate.distiller import _WIKI_CORPUS_REL, _densify, is_wiki_stale, main
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


def test_changed_kind_set_leaves_no_orphaned_articles(tmp_path):
    """A second distill with a changed non-empty-kind set clears orphans (WR-02).

    Run 1 has only INSIGHT -> 01-insights.md. Run 2 adds DECISION, which is
    ordered first, so DECISION becomes 01-decisions.md and INSIGHT shifts to
    02-insights.md. Without clearing, the run-1 01-insights.md would orphan
    alongside the run-2 02-insights.md and be ingested as a duplicate article.
    """
    corpus_dir = tmp_path / _WIKI_CORPUS_REL

    _seed(tmp_path, [MemoryKind.INSIGHT])
    assert main(["--root", str(tmp_path)]) == 0
    run1 = {p.name for p in corpus_dir.glob("*.md")}
    assert run1 == {"01-insights.md"}

    # Add a higher-priority kind so the filename numbering shifts. --force
    # mirrors the CLI, which always passes it (the staleness decision is made
    # upstream in cli.distill), bypassing the distiller's populated-corpus skip.
    _seed(tmp_path, [MemoryKind.DECISION])
    assert main(["--root", str(tmp_path), "--force"]) == 0
    run2 = {p.name for p in corpus_dir.glob("*.md")}

    # Exactly the current article set — the orphaned 01-insights.md is gone.
    assert run2 == {"01-decisions.md", "02-insights.md"}


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


def _populate_corpus(root: Path) -> None:
    """Write a minimal on-disk wiki corpus so is_wiki_stale exercises the mtime
    comparison rather than short-circuiting on the WR-01 corpus-present guard."""
    corpus_dir = root / _WIKI_CORPUS_REL
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "01-decisions.md").write_text("# Decision\n")


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
    _populate_corpus(tmp_path)
    state = _state_with_wiki_entry(datetime.now(UTC) + timedelta(hours=1))
    assert is_wiki_stale(tmp_path, state) is False


def test_is_wiki_stale_memory_touched_after_entry_is_stale(tmp_path):
    """memory.db mtime newer than the entry created_at -> stale."""
    _seed(tmp_path, [MemoryKind.DECISION])
    state = _state_with_wiki_entry(datetime.now(UTC) - timedelta(hours=1))
    assert is_wiki_stale(tmp_path, state) is True


def test_is_wiki_stale_absent_memory_db_not_stale(tmp_path):
    """Entry present but no memory.db on disk -> not stale (nothing to regenerate from)."""
    _populate_corpus(tmp_path)
    state = _state_with_wiki_entry(datetime.now(UTC))
    assert is_wiki_stale(tmp_path, state) is False


def test_is_wiki_stale_missing_corpus_is_stale_despite_fresh_entry(tmp_path):
    """Entry newer than memory.db but corpus dir absent -> stale (WR-01).

    A manifest entry can outlive the corpus it describes when
    .planning/codebase/wiki/ is deleted while memory.db is untouched. The gate
    must report stale so --force regeneration is not refused.
    """
    _seed(tmp_path, [MemoryKind.DECISION])
    state = _state_with_wiki_entry(datetime.now(UTC) + timedelta(hours=1))
    # No corpus directory on disk at all.
    assert not (tmp_path / _WIKI_CORPUS_REL).exists()
    assert is_wiki_stale(tmp_path, state) is True


def test_is_wiki_stale_empty_corpus_dir_is_stale_despite_fresh_entry(tmp_path):
    """Entry newer than memory.db but corpus dir has no *.md -> stale (WR-01)."""
    _seed(tmp_path, [MemoryKind.DECISION])
    state = _state_with_wiki_entry(datetime.now(UTC) + timedelta(hours=1))
    corpus_dir = tmp_path / _WIKI_CORPUS_REL
    corpus_dir.mkdir(parents=True)  # present but empty (no article files)
    assert is_wiki_stale(tmp_path, state) is True


# ---------------------------------------------------------------------------
# Task 3: _densify routes through wrap("llm") (SBX-03) + main resolves tier
# ---------------------------------------------------------------------------


class TestDensifySandboxWrap:
    """distiller.py's claude densify call routes through wrap('llm') (SBX-03)."""

    def test_densify_scrubs_secrets_preserves_auth(self, tmp_path, monkeypatch):
        """Explicit scrubbed env: auth vars survive, credential-shaped vars dropped."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-secret")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(cmd, 0, stdout="densified\n", stderr="")

        monkeypatch.setattr("flowstate.distiller.subprocess.run", fake_run)

        result = _densify("article text", "claude", "opus", root=tmp_path, tier="observe")

        assert result == "densified\n"
        env = captured["env"]
        assert env is not None
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"
        assert "AWS_SECRET_ACCESS_KEY" not in env

    def test_densify_subprocess_failure_returns_original_text(self, tmp_path, monkeypatch):
        """Degradation contract intact: any subprocess failure -> original text unchanged."""

        def _boom(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr("flowstate.distiller.subprocess.run", _boom)
        result = _densify("original text", "claude", "opus", root=tmp_path, tier="observe")
        assert result == "original text"


def test_distill_main_resolves_tier_from_saved_preferences(tmp_path, monkeypatch):
    """distill main resolves tier from load_state(root).preferences.sandbox
    (defaults to 'observe' on a fresh root with no flowstate.json)."""
    _seed(tmp_path, [MemoryKind.DECISION])
    monkeypatch.setattr("flowstate.distiller._locate_claude", lambda: "/bin/claude")

    captured_tier = {}

    def fake_densify(article_text, claude, model, root, *, tier="observe"):
        captured_tier["tier"] = tier
        return article_text

    monkeypatch.setattr("flowstate.distiller._densify", fake_densify)

    rc = main(["--root", str(tmp_path), "--llm"])
    assert rc == 0
    assert captured_tier["tier"] == "observe"


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
