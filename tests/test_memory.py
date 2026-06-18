"""Tests for flowstate.memory — MemoryStore with SQLite FTS5."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

# ---------------------------------------------------------------------------
# sqlite_vec availability guard — mirrors bench/grounding.py test pattern
# ---------------------------------------------------------------------------
try:
    import sqlite_vec  # noqa: F401

    _HAS_VEC = True
except Exception:
    _HAS_VEC = False


def _fake_embedder(dim: int = 4):
    """Return a get_embedder-compatible Embedder backed by a deterministic fake embed_fn."""
    from flowstate.embeddings import get_embedder

    def embed_fn(texts: list[str]) -> list[list[float]]:
        result = []
        for t in texts:
            # Deterministic: hash the text mod dim to produce a unit-ish vector
            base = [float((hash(t) >> i) & 0xFF) / 255.0 for i in range(dim)]
            result.append(base)
        return result

    return get_embedder(embed_fn=embed_fn)


def _unavailable_embedder():
    """Return an Embedder whose available() is False (simulates fastembed absent)."""
    from flowstate.embeddings import Embedder

    e = Embedder(model_name="none")
    e._unavailable = True  # mark as permanently unavailable
    return e


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s


@pytest.fixture()
def populated_store(store: MemoryStore) -> MemoryStore:
    entries = [
        MemoryEntry.create(
            MemoryKind.RESEARCH,
            "Kafka Streams provides lightweight stream processing built on Kafka consumer groups.",
            "Kafka Streams overview",
            source="research/report.md",
            tags=["kafka", "streaming"],
            run_id="run-001",
        ),
        MemoryEntry.create(
            MemoryKind.RESEARCH,
            "Flink SQL supports TUMBLE, HOP, and SESSION window functions for event-time processing.",
            "Flink SQL window functions",
            source="research/report.md",
            tags=["flink", "sql", "windows"],
            run_id="run-001",
        ),
        MemoryEntry.create(
            MemoryKind.STRATEGY,
            "NLP-to-SQL approach validated. Risk: complex joins may need manual review.",
            "Strategy pressure test result",
            source="research/strategy.md",
            tags=["strategy", "nlp"],
            run_id="run-001",
        ),
        MemoryEntry.create(
            MemoryKind.DECISION,
            "Using event-driven architecture with Kafka as the backbone.",
            "Architecture decision: event-driven",
            tags=["architecture"],
            run_id="run-001",
        ),
        MemoryEntry.create(
            MemoryKind.TOOL_RUN,
            "Research tool failed: timeout after 60s on topic 'schema registry'.",
            "Research failure: schema registry",
            source="research",
            tags=["failure", "timeout"],
            run_id="run-001",
        ),
    ]
    store.add_many(entries)
    return store


class TestMemoryEntry:
    def test_create_generates_id(self):
        entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
        assert len(entry.id) == 12
        assert entry.kind == MemoryKind.RESEARCH
        assert entry.content == "content"
        assert entry.summary == "summary"

    def test_create_unique_ids(self):
        e1 = MemoryEntry.create(MemoryKind.RESEARCH, "a", "b")
        e2 = MemoryEntry.create(MemoryKind.RESEARCH, "a", "b")
        assert e1.id != e2.id

    def test_create_with_all_fields(self):
        entry = MemoryEntry.create(
            MemoryKind.STRATEGY,
            "content",
            "summary",
            source="test.md",
            tags=["a", "b"],
            metadata={"key": "val"},
            run_id="run-123",
        )
        assert entry.source == "test.md"
        assert entry.tags == ["a", "b"]
        assert entry.metadata == {"key": "val"}
        assert entry.run_id == "run-123"


class TestMemoryStoreCRUD:
    def test_add_and_get(self, store: MemoryStore):
        entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
        returned_id = store.add(entry)
        assert returned_id == entry.id

        got = store.get(entry.id)
        assert got is not None
        assert got.content == "content"
        assert got.kind == MemoryKind.RESEARCH

    def test_get_nonexistent(self, store: MemoryStore):
        assert store.get("nonexistent") is None

    def test_add_many(self, store: MemoryStore):
        entries = [
            MemoryEntry.create(MemoryKind.RESEARCH, f"content-{i}", f"summary-{i}")
            for i in range(5)
        ]
        ids = store.add_many(entries)
        assert len(ids) == 5
        assert store.count() == 5

    def test_get_by_kind(self, populated_store: MemoryStore):
        research = populated_store.get_by_kind(MemoryKind.RESEARCH)
        assert len(research) == 2
        assert all(e.kind == MemoryKind.RESEARCH for e in research)

    def test_get_by_kind_with_limit(self, populated_store: MemoryStore):
        research = populated_store.get_by_kind(MemoryKind.RESEARCH, limit=1)
        assert len(research) == 1

    def test_count_all(self, populated_store: MemoryStore):
        assert populated_store.count() == 5

    def test_count_by_kind(self, populated_store: MemoryStore):
        assert populated_store.count(MemoryKind.RESEARCH) == 2
        assert populated_store.count(MemoryKind.STRATEGY) == 1
        assert populated_store.count(MemoryKind.DECISION) == 1
        assert populated_store.count(MemoryKind.TOOL_RUN) == 1
        assert populated_store.count(MemoryKind.INSIGHT) == 0

    def test_clear(self, populated_store: MemoryStore):
        deleted = populated_store.clear()
        assert deleted == 5
        assert populated_store.count() == 0


class TestFTS5Search:
    def test_search_by_keyword(self, populated_store: MemoryStore):
        results = populated_store.search("kafka")
        assert len(results) >= 1
        assert any("Kafka" in r.entry.content for r in results)

    def test_search_by_kind(self, populated_store: MemoryStore):
        results = populated_store.search("kafka", kind=MemoryKind.RESEARCH)
        assert len(results) >= 1
        assert all(r.entry.kind == MemoryKind.RESEARCH for r in results)

    def test_search_no_results(self, populated_store: MemoryStore):
        results = populated_store.search("nonexistent_xyzzy")
        assert len(results) == 0

    def test_search_empty_query(self, populated_store: MemoryStore):
        results = populated_store.search("")
        assert len(results) == 0

    def test_search_with_limit(self, populated_store: MemoryStore):
        results = populated_store.search("kafka OR flink OR NLP", limit=2)
        assert len(results) <= 2

    def test_search_scores_positive(self, populated_store: MemoryStore):
        results = populated_store.search("kafka")
        assert all(r.score > 0 for r in results)

    def test_search_relevance_ordering(self, populated_store: MemoryStore):
        results = populated_store.search("flink SQL window")
        assert len(results) >= 1
        assert "Flink SQL" in results[0].entry.summary

    def test_porter_stemming(self, populated_store: MemoryStore):
        results = populated_store.search("streaming")
        assert len(results) >= 1


class TestGetContext:
    def test_get_context_returns_markdown(self, populated_store: MemoryStore):
        ctx = populated_store.get_context("kafka streaming")
        assert ctx.startswith("## Prior Knowledge")
        assert "###" in ctx

    def test_get_context_empty_on_no_match(self, populated_store: MemoryStore):
        ctx = populated_store.get_context("nonexistent_xyzzy")
        assert ctx == ""

    def test_get_context_respects_budget(self, store: MemoryStore):
        for i in range(20):
            store.add(
                MemoryEntry.create(
                    MemoryKind.RESEARCH,
                    f"Long content about topic {i}. " * 50,
                    f"Topic {i} research",
                    tags=["test"],
                )
            )
        ctx = store.get_context("topic", max_tokens=500)
        assert len(ctx) < 500 * 4 + 200  # budget + overhead


class TestLastEntryAt:
    def test_empty_store_returns_none(self, tmp_path: Path):
        with MemoryStore(root=tmp_path) as store:
            assert store.last_entry_at() is None

    def test_returns_most_recent_timestamp(self, tmp_path: Path):
        import time
        from datetime import datetime

        with MemoryStore(root=tmp_path) as store:
            store.add(MemoryEntry.create(MemoryKind.RESEARCH, "first", "s1"))
            time.sleep(0.01)
            store.add(MemoryEntry.create(MemoryKind.DECISION, "second", "s2"))
            ts = store.last_entry_at()
            assert ts is not None
            assert isinstance(ts, datetime)


class TestMemoryKindRUN:
    def test_run_kind_value(self):
        assert MemoryKind.RUN == "run"

    def test_count_includes_run(self, store: MemoryStore):
        assert store.count(MemoryKind.RUN) == 0

    def test_add_run_entry_and_get_by_kind(self, store: MemoryStore):
        entry = MemoryEntry.create(
            MemoryKind.RUN,
            "Pipeline run delta: first run",
            "run abc123",
            source="journal",
            tags=["run"],
            run_id="abc123",
        )
        store.add(entry)
        results = store.get_by_kind(MemoryKind.RUN, limit=1)
        assert len(results) == 1
        assert results[0].kind == MemoryKind.RUN
        assert results[0].run_id == "abc123"


class TestPersistence:
    def test_data_persists_across_reopen(self, tmp_path: Path):
        entry = MemoryEntry.create(MemoryKind.RESEARCH, "persistent data", "test persistence")

        with MemoryStore(root=tmp_path) as store:
            store.add(entry)

        with MemoryStore(root=tmp_path) as store2:
            got = store2.get(entry.id)
            assert got is not None
            assert got.content == "persistent data"

    def test_search_works_after_reopen(self, tmp_path: Path):
        entry = MemoryEntry.create(
            MemoryKind.RESEARCH,
            "kafka streaming data",
            "kafka test",
            tags=["kafka"],
        )

        with MemoryStore(root=tmp_path) as store:
            store.add(entry)

        with MemoryStore(root=tmp_path) as store2:
            results = store2.search("kafka")
            assert len(results) == 1

    def test_db_file_created(self, tmp_path: Path):
        with MemoryStore(root=tmp_path):
            pass
        assert (tmp_path / "memory.db").exists()


class TestMemoryStoreUpdate:
    def test_update_mutates_fields(self, store: MemoryStore):
        """update() stores mutated metadata + summary; get() reflects the new values."""
        entry = MemoryEntry.create(
            MemoryKind.INSIGHT,
            "original content",
            "original summary",
            metadata={"count": 1, "first_seen": "2026-01-01T00:00:00+00:00"},
        )
        store.add(entry)

        # Mutate in-place and update
        entry.metadata["count"] = 2
        entry.metadata["last_seen"] = "2026-01-02T00:00:00+00:00"
        entry.summary = "updated summary"
        store.update(entry)

        got = store.get(entry.id)
        assert got is not None
        assert got.summary == "updated summary"
        assert got.metadata["count"] == 2
        assert got.metadata["last_seen"] == "2026-01-02T00:00:00+00:00"
        # first_seen unchanged
        assert got.metadata["first_seen"] == "2026-01-01T00:00:00+00:00"

    def test_update_resyncs_fts(self, store: MemoryStore):
        """After update(), FTS search finds the new summary token and NOT the old-only token."""
        entry = MemoryEntry.create(
            MemoryKind.INSIGHT,
            "old content text",
            "old unique summary token xylophone",
        )
        store.add(entry)

        # Verify old token is searchable
        assert len(store.search("xylophone")) >= 1

        # Update to new summary
        entry.summary = "new unique summary token zeppelin"
        entry.content = "new content text"
        store.update(entry)

        # New token should be found; old unique token should NOT be found
        new_results = store.search("zeppelin")
        old_results = store.search("xylophone")
        assert len(new_results) >= 1
        assert len(old_results) == 0

    def test_update_nonexistent_id_is_noop(self, store: MemoryStore):
        """update() on a non-existent id does not raise and leaves store empty."""
        entry = MemoryEntry.create(MemoryKind.INSIGHT, "ghost content", "ghost summary")
        # Do NOT add — entry has a valid id but no row in DB
        store.update(entry)  # must not raise
        assert store.count() == 0

    def test_get_gotchas_returns_only_gotcha_tagged_insight(self, store: MemoryStore):
        """get_gotchas() returns only INSIGHT entries tagged 'gotcha', regardless of total count."""
        from flowstate.memory import MemoryEntry, MemoryKind

        # Add 5 non-gotcha INSIGHT entries
        for i in range(5):
            store.add(MemoryEntry.create(MemoryKind.INSIGHT, f"research {i}", f"summary {i}"))

        # Add 2 gotcha INSIGHT entries
        g1 = MemoryEntry.create(
            MemoryKind.INSIGHT, "gotcha one", "gotcha one", tags=["gotcha", "doctor"]
        )
        g2 = MemoryEntry.create(
            MemoryKind.INSIGHT, "gotcha two", "gotcha two", tags=["gotcha", "verifier"]
        )
        store.add(g1)
        store.add(g2)

        gotchas = store.get_gotchas()
        assert len(gotchas) == 2
        assert all("gotcha" in e.tags for e in gotchas)

    def test_delete_removes_entry(self, store: MemoryStore):
        """delete() removes entry by id; FTS trigger fires via memories_ad."""
        from flowstate.memory import MemoryEntry, MemoryKind

        entry = MemoryEntry.create(MemoryKind.INSIGHT, "to delete", "summary")
        store.add(entry)
        assert store.count() == 1

        store.delete(entry.id)
        assert store.count() == 0
        assert store.get(entry.id) is None

    def test_delete_nonexistent_is_noop(self, store: MemoryStore):
        """delete() on a non-existent id does not raise."""
        store.delete("nonexistent000")  # must not raise
        assert store.count() == 0


# ---------------------------------------------------------------------------
# Task 1 tests: sqlite-vec load, memories_vec creation, embed-on-write
# ---------------------------------------------------------------------------


class TestMemoriesVecTable:
    """memories_vec table creation and sqlite-vec load behavior."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_memories_vec_created_on_open(self, tmp_path: Path):
        """Opening a fresh store creates memories_vec when sqlite_vec loads."""
        with MemoryStore(root=tmp_path) as store:
            assert store._vec_ready is True
            row = store._conn.execute(
                "SELECT name FROM sqlite_master WHERE name='memories_vec'"
            ).fetchone()
            assert row is not None, "memories_vec table missing despite _vec_ready=True"

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_store_opens_on_existing_db_without_migration(self, tmp_path: Path):
        """Opening an existing db does not raise and does not require a migration command."""
        with MemoryStore(root=tmp_path) as s1:
            s1.add(MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary"))
        # Reopen — must not raise
        with MemoryStore(root=tmp_path) as s2:
            assert s2.count() == 1

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_add_returns_entry_id_unchanged(self, tmp_path: Path):
        """add() still returns entry.id (return type unchanged)."""
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
            returned = store.add(entry)
            assert returned == entry.id

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_add_with_embedder_writes_one_vec_row(self, tmp_path: Path):
        """add() with a fake embedder writes exactly one memories_vec row keyed to the memory rowid."""
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
            store.add(entry)

            mem_rowid = store._conn.execute(
                "SELECT rowid FROM memories WHERE id=?", (entry.id,)
            ).fetchone()[0]

            vec_count = store._conn.execute(
                "SELECT COUNT(*) FROM memories_vec WHERE rowid=?", (mem_rowid,)
            ).fetchone()[0]
            assert vec_count == 1

    def test_add_without_embedder_writes_zero_vec_rows(self, tmp_path: Path):
        """add() with embedder absent (available()==False) writes zero vec rows and does not raise."""
        with MemoryStore(root=tmp_path, embedder=_unavailable_embedder()) as store:
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
            store.add(entry)  # must not raise

            if store._vec_ready:
                count = store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
                assert count == 0

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_add_many_with_embedder_writes_one_row_per_entry(self, tmp_path: Path):
        """add_many() with a fake embedder writes one memories_vec row per entry."""
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(3)
            ]
            store.add_many(entries)

            count = store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            assert count == 3

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_add_many_without_embedder_writes_zero_vec_rows(self, tmp_path: Path):
        """add_many() with embedder absent (available()==False) writes zero vec rows and does not raise."""
        with MemoryStore(root=tmp_path, embedder=_unavailable_embedder()) as store:
            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(2)
            ]
            store.add_many(entries)  # must not raise

            if store._vec_ready:
                count = store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
                assert count == 0

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_update_replaces_vec_row(self, tmp_path: Path):
        """update() with a fake embedder replaces the memories_vec row (still exactly one row)."""
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "original content", "original summary")
            store.add(entry)

            mem_rowid = store._conn.execute(
                "SELECT rowid FROM memories WHERE id=?", (entry.id,)
            ).fetchone()[0]

            # Update the entry
            entry.content = "updated content"
            entry.summary = "updated summary"
            store.update(entry)

            vec_count = store._conn.execute(
                "SELECT COUNT(*) FROM memories_vec WHERE rowid=?", (mem_rowid,)
            ).fetchone()[0]
            assert vec_count == 1  # still exactly one row, not duplicated

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_load_extension_disabled_after_load(self, tmp_path: Path):
        """enable_load_extension(False) re-scopes extension surface after sqlite_vec loads.

        After the re-scope, load_extension() should raise OperationalError because
        the load-extension permission has been withdrawn.
        """
        import sqlite3

        with MemoryStore(root=tmp_path) as store:
            assert store._vec_ready is True
            # load_extension should now raise — the load-extension permission was disabled
            with pytest.raises(sqlite3.OperationalError):
                store._conn.load_extension("nonexistent_extension_xyz")

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_vec_ready_flag_present(self, tmp_path: Path):
        """_vec_ready attribute is set on MemoryStore."""
        with MemoryStore(root=tmp_path) as store:
            assert hasattr(store, "_vec_ready")


# ---------------------------------------------------------------------------
# Task 2 tests: lazy backfill on open
# ---------------------------------------------------------------------------


class TestLazyBackfill:
    """Lazy vector backfill on MemoryStore open."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_backfill_on_reopen_with_embedder(self, tmp_path: Path):
        """Pre-populate memories without vec rows; reopen with embedder → all rows backfilled.

        Backfill is deferred to the first write (VEC-03: open never blocks startup).
        Strategy: add entries, clear vec rows to simulate un-vectored state, reopen,
        then trigger a write to kick off backfill and assert all rows are backfilled.
        """
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(3)
            ]
            store.add_many(entries)
            # Simulate un-vectored state by clearing the vec table
            store._conn.execute("DELETE FROM memories_vec")
            store._conn.commit()
            assert store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0] == 0

        # Reopen with same-dim embedder; trigger a write to kick off deferred backfill
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store2:
            assert store2._vec_ready is True
            # Trigger backfill by writing one new entry (backfill runs before insert)
            store2.add(MemoryEntry.create(MemoryKind.RESEARCH, "trigger", "trigger"))
            vec_count = store2._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            mem_count = store2.count()
            assert vec_count == mem_count, (
                f"expected {mem_count} vec rows after backfill, got {vec_count}"
            )

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_backfill_is_idempotent(self, tmp_path: Path):
        """Reopening a fully-backfilled store adds zero duplicate vec rows."""
        embedder = _fake_embedder(dim=4)

        # First open with embedder — rows embed on add
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(2)
            ]
            store.add_many(entries)

        # Second open with embedder — backfill is a no-op; no duplicates
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store2:
            vec_count = store2._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            assert vec_count == 2  # same count, no duplicates

    def test_backfill_without_embedder_is_noop(self, tmp_path: Path):
        """Opening a store with no embedder is a no-op and does not raise."""
        with MemoryStore(root=tmp_path) as store:
            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(2)
            ]
            store.add_many(entries)

        # Reopen without embedder — must not raise
        with MemoryStore(root=tmp_path) as store2:
            assert store2.count() == 2  # FTS5 path unaffected


# ---------------------------------------------------------------------------
# Fix-coverage tests: CR-01, WR-01, WR-02, WR-03, WR-04, WR-05
# ---------------------------------------------------------------------------


class TestCR01ExtensionRescope:
    """CR-01: enable_load_extension(False) must run even when sqlite_vec.load() raises."""

    def test_extension_disabled_after_load_failure(self, tmp_path: Path, monkeypatch):
        """When sqlite_vec.load() raises, enable_load_extension(False) must still run.

        _vec_ready must be False and the connection must not allow load_extension().
        Uses sys.modules patching to inject a fake sqlite_vec whose load() raises.
        """
        import sqlite3
        import sys
        import types

        def failing_load(conn):
            raise RuntimeError("simulated load failure")

        # Patch sqlite_vec in sys.modules so the local import inside _init_vec
        # gets our fake module, but .load() raises.
        fake_vec = types.ModuleType("sqlite_vec")
        fake_vec.load = failing_load  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "sqlite_vec", fake_vec)

        with MemoryStore(root=tmp_path) as store:
            # _vec_ready must be False after load failure
            assert store._vec_ready is False
            # The connection must NOT allow load_extension (re-scoped off in finally)
            with pytest.raises(sqlite3.OperationalError):
                store._conn.load_extension("nonexistent_extension_xyz")


class TestWR01NoModelLoadOnOpen:
    """WR-01: Opening MemoryStore with the default embedder must NOT construct the real model."""

    def test_default_embedder_open_does_not_construct_model(self, tmp_path: Path, monkeypatch):
        """MemoryStore(root) must not call TextEmbedding() during __init__ (VEC-03)."""
        import flowstate.embeddings as emb

        constructed = []

        class SentinelTextEmbedding:
            def __init__(self, *args, **kwargs):
                constructed.append(args)

            def embed(self, texts):
                return iter([[0.0] * emb._DEFAULT_DIM])

        # Patch at the module level — _ensure_model() imports from this.
        monkeypatch.setattr(emb, "TextEmbedding", SentinelTextEmbedding, raising=False)
        # Also patch the fastembed import inside _ensure_model so it returns our sentinel.
        import builtins

        real_import = builtins.__import__

        def patched_import(name, *args, **kwargs):
            if name == "fastembed":
                import types

                fake = types.ModuleType("fastembed")
                fake.TextEmbedding = SentinelTextEmbedding  # type: ignore[attr-defined]
                return fake
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", patched_import)

        # Open the store — must complete without constructing SentinelTextEmbedding.
        with MemoryStore(root=tmp_path):
            pass

        assert constructed == [], (
            "TextEmbedding was constructed during MemoryStore open — startup would block/download"
        )

    def test_configured_dim_does_not_load_model(self, monkeypatch):
        """Embedder.configured_dim returns _DEFAULT_DIM without constructing the model."""
        from flowstate.embeddings import _DEFAULT_DIM, Embedder

        constructed = []

        class SentinelModel:
            def __init__(self, *args, **kwargs):
                constructed.append(1)

        e = Embedder(model_name="BAAI/bge-small-en-v1.5")
        # configured_dim should return _DEFAULT_DIM without ever touching _ensure_model
        assert e.configured_dim == _DEFAULT_DIM
        assert constructed == [], "configured_dim triggered model construction"
        assert e._model is None  # model was never loaded
        assert e._unavailable is False  # no load was attempted


class TestWR02DimMismatch:
    """WR-02: Dim mismatch on reopen must set _vec_ready=False rather than silently diverging."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_dim_mismatch_on_reopen_sets_vec_not_ready(self, tmp_path: Path):
        """If memories_vec was created with dim=4 but embedder now reports dim=8,
        _vec_ready must be False and add() must not raise (FTS5 path unaffected)."""
        # First open: create db with dim=4 embedder
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store:
            store.add(MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary"))
            assert store._vec_ready is True

        # Reopen with a different dim — must detect mismatch and degrade gracefully
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=8)) as store2:
            assert store2._vec_ready is False, "dim mismatch should have set _vec_ready=False"
            # FTS5 path must be unaffected: add/search still work
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "new content", "new summary")
            returned_id = store2.add(entry)  # must not raise
            assert returned_id == entry.id
            assert store2.count() == 2
            assert len(store2.search("content")) >= 1


class TestWR03NarrowExcept:
    """WR-03: sqlite3.Error in embed path must flip _vec_ready=False; FTS5 still works."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_sqlite_error_in_embed_disables_vec_not_fts5(self, tmp_path: Path):
        """When INSERT INTO memories_vec raises a dimension error (sqlite3.Error),
        _vec_ready flips to False and the store degrades to FTS5-only without raising.

        Strategy: create table with dim=4, then swap in a dim=8 embed_fn so that
        _embed_rowid produces a vector of wrong length, causing sqlite3.Error on INSERT.
        _vec_ready must be set to False; add() must not raise; FTS5 still works.
        """
        # Create the store with dim=4 table, confirm it works
        embedder = _fake_embedder(dim=4)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            assert store._vec_ready is True
            store.add(MemoryEntry.create(MemoryKind.RESEARCH, "first", "first summary"))
            assert store.count() == 1

            # Swap the embedder's embed_fn to produce dim=8 vectors into a float[4] table.
            # The INSERT will raise sqlite3.Error (dimension mismatch).
            store._embedder._embed_fn = _fake_embedder(dim=8)._embed_fn

            entry = MemoryEntry.create(MemoryKind.RESEARCH, "second", "second summary")
            returned_id = store.add(entry)  # must not raise

            assert returned_id == entry.id  # add() return unchanged
            assert store._vec_ready is False  # sqlite3.Error flipped the flag
            assert store.count() == 2  # FTS5 path: row was stored
            assert len(store.search("second")) >= 1  # FTS5 search still works


class TestWR04AddManyAtomicVec:
    """WR-04: add_many vec writes must be all-or-nothing; failure rolls back vec side."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_add_many_vec_failure_rolls_back_all_vec_rows(self, tmp_path: Path):
        """If vec INSERT fails mid-loop in add_many, all vec rows for that call are rolled
        back (memories rows remain intact); _vec_ready goes False; store reconciles on reopen.

        Strategy: create table with dim=4, add a warm-up entry to confirm vec works,
        then swap the embed_fn to dim=8 on the SECOND add_many call so that the first
        INSERT inside add_many succeeds but the second raises (dim mismatch). This
        exercises the savepoint rollback path.
        """
        # Open store with dim=4; add a first entry to confirm vec is working
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store:
            assert store._vec_ready is True
            store.add(MemoryEntry.create(MemoryKind.RESEARCH, "warmup", "warmup"))
            assert store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0] == 1

            # Now swap to dim=8 embed_fn — subsequent INSERTs will raise dim error
            call_count = [0]
            dim4_fn = _fake_embedder(dim=4)._embed_fn
            dim8_fn = _fake_embedder(dim=8)._embed_fn

            def mixed_fn(texts):
                call_count[0] = call_count[0] + 1
                if call_count[0] >= 2:
                    return dim8_fn(texts)  # wrong dim → sqlite3.Error on INSERT
                return dim4_fn(texts)

            store._embedder._embed_fn = mixed_fn

            entries = [
                MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}")
                for i in range(3)
            ]
            ids = store.add_many(entries)  # must not raise

            assert len(ids) == 3  # all memory IDs returned
            assert store.count() == 4  # 1 warmup + 3 new memories rows committed
            # Vec writes rolled back — _vec_ready is False; zero vec rows added by add_many
            assert store._vec_ready is False
            vec_count = store._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            assert vec_count == 1  # only the warmup row; add_many's rows were rolled back

        # Reopen: memories intact; backfill reconciles on first write
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store2:
            assert store2.count() == 4  # FTS5 path unaffected
            # Trigger backfill by writing — should reconcile all rows
            store2.add(MemoryEntry.create(MemoryKind.RESEARCH, "trigger", "trigger"))
            vec_count = store2._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            assert vec_count == store2.count()  # all rows backfilled after reconcile


class TestWR05BackfillBatchLimit:
    """WR-05: backfill must respect _BACKFILL_BATCH and not block startup on large dbs."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_backfill_batch_limit_respected(self, tmp_path: Path, monkeypatch):
        """When more than _BACKFILL_BATCH rows are un-vectored, backfill processes at most
        _BACKFILL_BATCH of them per open (WR-05: no unbounded startup scan)."""
        import flowstate.memory as mem_mod

        # Set a very small batch for this test
        monkeypatch.setattr(mem_mod.MemoryStore, "_BACKFILL_BATCH", 2)

        embedder = _fake_embedder(dim=4)
        # First open: add 5 entries with embedder so table is created at correct dim
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            for i in range(5):
                store.add(MemoryEntry.create(MemoryKind.RESEARCH, f"content {i}", f"summary {i}"))
            # Clear vec rows to simulate un-vectored state
            store._conn.execute("DELETE FROM memories_vec")
            store._conn.commit()

        # Reopen and trigger backfill via a write — should process at most 2 rows
        with MemoryStore(root=tmp_path, embedder=_fake_embedder(dim=4)) as store2:
            assert store2._vec_ready is True
            store2.add(MemoryEntry.create(MemoryKind.RESEARCH, "trigger", "trigger"))
            vec_count = store2._conn.execute("SELECT COUNT(*) FROM memories_vec").fetchone()[0]
            # batch=2 backfill + 1 for the trigger add = 3; never 6 (all at once)
            assert vec_count <= 3, (
                f"backfill processed more than _BACKFILL_BATCH rows ({vec_count} > 3)"
            )
            assert vec_count >= 1  # at least the trigger entry was embedded
