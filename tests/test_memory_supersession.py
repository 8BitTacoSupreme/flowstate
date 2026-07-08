"""Tests for deterministic supersession in flowstate.memory.

Covers: schema migration, supersede() API, retrieval exclusion, byte-identical
baseline, and find_contradiction_candidates() — all in self-contained style
matching tests/test_memory.py conventions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

# ---------------------------------------------------------------------------
# sqlite_vec availability guard — mirrors test_memory.py pattern
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
            base = [float((hash(t) >> i) & 0xFF) / 255.0 for i in range(dim)]
            result.append(base)
        return result

    return get_embedder(embed_fn=embed_fn)


def _unavailable_embedder():
    """Return an Embedder whose available() is False (simulates fastembed absent)."""
    from flowstate.embeddings import Embedder

    e = Embedder(model_name="none")
    e._unavailable = True
    return e


# ---------------------------------------------------------------------------
# Helpers for building a pre-v2 memory.db
# ---------------------------------------------------------------------------

_OLD_MEMORIES_DDL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);

CREATE TABLE IF NOT EXISTS memories (
    rowid INTEGER PRIMARY KEY,
    id TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT ''
);
"""


def _make_pre_v2_db(db_path: Path) -> str:
    """Create a pre-v2 memory.db (no superseded_by column) with one row. Returns the row id."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_OLD_MEMORIES_DDL)
    entry_id = "legacy000001"
    conn.execute(
        """INSERT INTO memories (id, kind, content, summary, source, tags, metadata, created_at, run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry_id,
            MemoryKind.RESEARCH.value,
            "legacy content from before supersession",
            "legacy summary",
            "",
            json.dumps(["legacy"]),
            json.dumps({}),
            datetime.now(UTC).isoformat(),
            "",
        ),
    )
    conn.commit()
    conn.close()
    return entry_id


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """Migration from pre-v2 (no superseded_by) to v2."""

    def test_migration_adds_superseded_by_column(self, tmp_path: Path):
        """Opening a pre-v2 db adds superseded_by column to memories."""
        db_path = tmp_path / "memory.db"
        _make_pre_v2_db(db_path)

        # Verify the column is absent BEFORE opening the store
        conn = sqlite3.connect(str(db_path))
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
        conn.close()
        assert "superseded_by" not in cols_before, "pre-condition: column should not exist yet"

        # Open MemoryStore — migration must fire
        with MemoryStore(root=tmp_path):
            pass

        # Verify column exists AFTER opening
        conn = sqlite3.connect(str(db_path))
        cols_after = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        conn.close()

        assert "superseded_by" in cols_after
        assert version == 2

    def test_migration_preserves_existing_rows_as_active(self, tmp_path: Path):
        """Pre-existing rows survive migration with superseded_by=None."""
        db_path = tmp_path / "memory.db"
        legacy_id = _make_pre_v2_db(db_path)

        with MemoryStore(root=tmp_path) as store:
            entry = store.get(legacy_id)
            assert entry is not None
            assert entry.superseded_by is None

    def test_migration_is_idempotent(self, tmp_path: Path):
        """Re-opening a migrated store does not raise or duplicate the column."""
        db_path = tmp_path / "memory.db"
        _make_pre_v2_db(db_path)

        # First open migrates
        with MemoryStore(root=tmp_path):
            pass

        # Second open must not raise
        with MemoryStore(root=tmp_path) as store2:
            conn = sqlite3.connect(str(db_path))
            cols = [row[1] for row in conn.execute("PRAGMA table_info(memories)")]
            conn.close()
            # Column appears exactly once
            assert cols.count("superseded_by") == 1
            assert store2.count() == 1  # row still there

    def test_fresh_db_schema_version_is_2(self, tmp_path: Path):
        """A brand-new MemoryStore records schema_version=2."""
        with MemoryStore(root=tmp_path) as store:
            row = store._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            assert row[0] == 2

    def test_migrated_db_schema_version_is_2(self, tmp_path: Path):
        """A migrated (pre-v2) MemoryStore records schema_version=2."""
        db_path = tmp_path / "memory.db"
        _make_pre_v2_db(db_path)

        with MemoryStore(root=tmp_path) as store:
            row = store._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            assert row[0] == 2


# ---------------------------------------------------------------------------
# Fresh DB / backward-compat tests
# ---------------------------------------------------------------------------


class TestFreshDb:
    """A brand-new store has superseded_by; add()/get() behave as before."""

    def test_fresh_db_has_superseded_by_column(self, tmp_path: Path):
        """New store has superseded_by in PRAGMA table_info."""
        with MemoryStore(root=tmp_path) as store:
            cols = {row[1] for row in store._conn.execute("PRAGMA table_info(memories)")}
            assert "superseded_by" in cols

    def test_new_entries_are_active(self, tmp_path: Path):
        """Entries added to a fresh store have superseded_by=None."""
        with MemoryStore(root=tmp_path) as store:
            entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
            eid = store.add(entry)
            got = store.get(eid)
            assert got is not None
            assert got.superseded_by is None

    def test_add_get_roundtrip_unchanged(self, tmp_path: Path):
        """add()/get() roundtrip still works; superseded_by does not break existing fields."""
        with MemoryStore(root=tmp_path) as store:
            entry = MemoryEntry.create(
                MemoryKind.STRATEGY,
                "strategy content",
                "strategy summary",
                tags=["a", "b"],
                run_id="run-xyz",
            )
            store.add(entry)
            got = store.get(entry.id)
            assert got is not None
            assert got.content == "strategy content"
            assert got.kind == MemoryKind.STRATEGY
            assert got.tags == ["a", "b"]
            assert got.run_id == "run-xyz"
            assert got.superseded_by is None


# ---------------------------------------------------------------------------
# supersede() API tests
# ---------------------------------------------------------------------------


class TestSupersede:
    """supersede() sets the pointer and returns bool; never raises."""

    def test_supersede_sets_pointer_returns_true(self, tmp_path: Path):
        """supersede(old, new) returns True; get(old).superseded_by == new.id."""
        with MemoryStore(root=tmp_path) as store:
            old = MemoryEntry.create(MemoryKind.RESEARCH, "old content", "old summary")
            new = MemoryEntry.create(MemoryKind.RESEARCH, "new content", "new summary")
            store.add(old)
            store.add(new)

            result = store.supersede(old.id, new.id)
            assert result is True

            got = store.get(old.id)
            assert got is not None
            assert got.superseded_by == new.id

    def test_supersede_new_entry_stays_active(self, tmp_path: Path):
        """supersede() does NOT touch the new entry; it remains active."""
        with MemoryStore(root=tmp_path) as store:
            old = MemoryEntry.create(MemoryKind.RESEARCH, "old content", "old summary")
            new = MemoryEntry.create(MemoryKind.RESEARCH, "new content", "new summary")
            store.add(old)
            store.add(new)
            store.supersede(old.id, new.id)

            got_new = store.get(new.id)
            assert got_new is not None
            assert got_new.superseded_by is None

    def test_supersede_unknown_old_returns_false(self, tmp_path: Path):
        """supersede("does-not-exist", anything) returns False; never raises."""
        with MemoryStore(root=tmp_path) as store:
            new = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
            store.add(new)
            result = store.supersede("nonexistent-id-xyz", new.id)
            assert result is False

    def test_supersede_does_not_require_new_id_to_exist(self, tmp_path: Path):
        """supersede(old_id, "phantom") returns True — new_id is not validated."""
        with MemoryStore(root=tmp_path) as store:
            old = MemoryEntry.create(MemoryKind.RESEARCH, "old content", "old summary")
            store.add(old)
            result = store.supersede(old.id, "phantom-id-that-does-not-exist")
            assert result is True
            got = store.get(old.id)
            assert got.superseded_by == "phantom-id-that-does-not-exist"

    def test_supersede_never_raises_on_bad_input(self, tmp_path: Path):
        """supersede() with any string inputs does not raise."""
        with MemoryStore(root=tmp_path) as store:
            try:
                store.supersede("", "")
                store.supersede("a" * 100, "b" * 100)
            except Exception as exc:
                pytest.fail(f"supersede raised unexpectedly: {exc}")

    def test_supersede_does_not_auto_delete_or_mutate_content(self, tmp_path: Path):
        """supersede() leaves row count unchanged; old entry still readable."""
        with MemoryStore(root=tmp_path) as store:
            old = MemoryEntry.create(MemoryKind.RESEARCH, "old content", "old summary")
            new = MemoryEntry.create(MemoryKind.RESEARCH, "new content", "new summary")
            store.add(old)
            store.add(new)
            before_count = store.count()
            store.supersede(old.id, new.id)
            after_count = store.count()
            assert before_count == after_count == 2

            # Content unchanged
            got = store.get(old.id)
            assert got.content == "old content"
            assert got.summary == "old summary"


# ---------------------------------------------------------------------------
# Retrieval exclusion tests (FTS path)
# ---------------------------------------------------------------------------


class TestRetrievalExclusion:
    """search() and get_context() exclude superseded rows by default."""

    def test_search_excludes_superseded_by_default(self, tmp_path: Path):
        """search('keyword') omits superseded entry's id."""
        with MemoryStore(root=tmp_path) as store:
            active = MemoryEntry.create(
                MemoryKind.RESEARCH, "kafka streaming active", "kafka active"
            )
            stale = MemoryEntry.create(MemoryKind.RESEARCH, "kafka streaming stale", "kafka stale")
            replacement = MemoryEntry.create(
                MemoryKind.RESEARCH, "kafka streaming replacement", "kafka replacement"
            )
            store.add(active)
            store.add(stale)
            store.add(replacement)
            store.supersede(stale.id, replacement.id)

            results = store.search("kafka")
            result_ids = {r.entry.id for r in results}
            assert stale.id not in result_ids, "superseded entry must be excluded by default"
            assert active.id in result_ids
            assert replacement.id in result_ids

    def test_search_include_superseded_true_restores_them(self, tmp_path: Path):
        """search(include_superseded=True) includes superseded entries."""
        with MemoryStore(root=tmp_path) as store:
            active = MemoryEntry.create(MemoryKind.RESEARCH, "flink streaming", "flink active")
            stale = MemoryEntry.create(MemoryKind.RESEARCH, "flink streaming stale", "flink stale")
            replacement = MemoryEntry.create(
                MemoryKind.RESEARCH, "flink streaming replacement", "flink replacement"
            )
            store.add(active)
            store.add(stale)
            store.add(replacement)
            store.supersede(stale.id, replacement.id)

            results_all = store.search("flink", include_superseded=True)
            result_ids = {r.entry.id for r in results_all}
            assert stale.id in result_ids, "include_superseded=True must include stale entry"

    def test_get_context_excludes_superseded_summary(self, tmp_path: Path):
        """get_context() text does not contain superseded entry's summary."""
        with MemoryStore(root=tmp_path) as store:
            active = MemoryEntry.create(
                MemoryKind.RESEARCH,
                "ksql stream processing details",
                "ksql overview active",
            )
            stale = MemoryEntry.create(
                MemoryKind.RESEARCH,
                "ksql stream processing old details",
                "ksql overview stale UNIQUETOKEN42",
            )
            replacement = MemoryEntry.create(
                MemoryKind.RESEARCH,
                "ksql stream processing new details",
                "ksql overview replacement",
            )
            store.add(active)
            store.add(stale)
            store.add(replacement)
            store.supersede(stale.id, replacement.id)

            ctx = store.get_context("ksql stream")
            assert "UNIQUETOKEN42" not in ctx, "superseded entry's unique token must not appear"


# ---------------------------------------------------------------------------
# Byte-identical golden tests (no supersession applied)
# ---------------------------------------------------------------------------


class TestByteIdenticalGolden:
    """With nothing superseded, search()/get_context() are byte-identical to baseline."""

    def test_search_byte_identical_when_nothing_superseded(self, tmp_path: Path):
        """Two identical stores with no supersession yield identical search() results."""
        entries = [
            MemoryEntry.create(
                MemoryKind.RESEARCH,
                "Kafka Streams provides lightweight stream processing built on Kafka.",
                "Kafka Streams overview",
                tags=["kafka", "streaming"],
            ),
            MemoryEntry.create(
                MemoryKind.STRATEGY,
                "NLP-to-SQL approach validated. Risk: complex joins.",
                "Strategy result",
                tags=["strategy", "nlp"],
            ),
        ]

        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()

        with MemoryStore(root=dir_a, embedder=_unavailable_embedder()) as store_a:
            store_a.add_many(entries)
            results_a = store_a.search("kafka")

        with MemoryStore(root=dir_b, embedder=_unavailable_embedder()) as store_b:
            store_b.add_many(entries)
            results_b = store_b.search("kafka")

        assert [(r.entry.id, r.score) for r in results_a] == [
            (r.entry.id, r.score) for r in results_b
        ], "search() must be byte-identical when nothing superseded"

    def test_get_context_byte_identical_when_nothing_superseded(self, tmp_path: Path):
        """get_context() string is byte-identical across two identical unsuperseded stores."""
        entries = [
            MemoryEntry.create(
                MemoryKind.RESEARCH,
                "Kafka Streams provides lightweight stream processing built on Kafka.",
                "Kafka Streams overview",
                tags=["kafka", "streaming"],
            ),
            MemoryEntry.create(
                MemoryKind.STRATEGY,
                "NLP-to-SQL approach validated. Risk: complex joins.",
                "Strategy result",
                tags=["strategy", "nlp"],
            ),
        ]

        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()

        with MemoryStore(root=dir_a, embedder=_unavailable_embedder()) as store_a:
            store_a.add_many(entries)
            ctx_a = store_a.get_context("kafka streaming")

        with MemoryStore(root=dir_b, embedder=_unavailable_embedder()) as store_b:
            store_b.add_many(entries)
            ctx_b = store_b.get_context("kafka streaming")

        assert ctx_a.startswith("## Prior Knowledge")
        assert ctx_a == ctx_b, "get_context() must be byte-identical when nothing superseded"


# ---------------------------------------------------------------------------
# find_contradiction_candidates tests
# ---------------------------------------------------------------------------


class TestFindContradictionCandidates:
    """find_contradiction_candidates() is flag-only: surfaces, never mutates, never raises."""

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_surfaces_near_duplicate_excluding_own_id(self, tmp_path: Path):
        """Near-identical vectors → other active entry surfaces; own id is excluded."""
        from flowstate.embeddings import get_embedder

        # Two entries whose embedded vectors are identical (max cosine similarity = 1.0)
        near_vec = [0.9, 0.1, 0.0, 0.0]

        def embed_fn(texts: list[str]) -> list[list[float]]:
            return [near_vec for _ in texts]

        embedder = get_embedder(embed_fn=embed_fn)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content one alpha", "summary one")
            e2 = MemoryEntry.create(MemoryKind.RESEARCH, "content two alpha", "summary two")
            store.add(e1)
            store.add(e2)

            candidates = store.find_contradiction_candidates(e1)
            candidate_ids = {c.entry.id for c in candidates}
            assert e1.id not in candidate_ids, "own id must be excluded"
            assert e2.id in candidate_ids, "near-identical active entry must surface"

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_excludes_superseded_entries(self, tmp_path: Path):
        """Superseded entries are excluded from contradiction candidates."""
        from flowstate.embeddings import get_embedder

        near_vec = [0.9, 0.1, 0.0, 0.0]

        def embed_fn(texts: list[str]) -> list[list[float]]:
            return [near_vec for _ in texts]

        embedder = get_embedder(embed_fn=embed_fn)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content one", "summary one")
            stale = MemoryEntry.create(MemoryKind.RESEARCH, "content stale", "summary stale")
            replacement = MemoryEntry.create(
                MemoryKind.RESEARCH, "content replacement", "summary replacement"
            )
            store.add(e1)
            store.add(stale)
            store.add(replacement)
            store.supersede(stale.id, replacement.id)

            candidates = store.find_contradiction_candidates(e1)
            candidate_ids = {c.entry.id for c in candidates}
            assert stale.id not in candidate_ids, "superseded entry must not surface as candidate"

    def test_returns_empty_when_embedder_unavailable(self, tmp_path: Path):
        """Returns [] when embedder is unavailable; never raises."""
        with MemoryStore(root=tmp_path, embedder=_unavailable_embedder()) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content one", "summary one")
            store.add(e1)

            candidates = store.find_contradiction_candidates(e1)
            assert candidates == []

    def test_mutates_nothing(self, tmp_path: Path):
        """find_contradiction_candidates() does not change count or superseded_by values."""
        with MemoryStore(root=tmp_path, embedder=_unavailable_embedder()) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content one", "summary one")
            e2 = MemoryEntry.create(MemoryKind.RESEARCH, "content two", "summary two")
            store.add(e1)
            store.add(e2)
            before_count = store.count()

            store.find_contradiction_candidates(e1)

            assert store.count() == before_count
            assert store.get(e1.id).superseded_by is None
            assert store.get(e2.id).superseded_by is None

    def test_never_raises_on_arbitrary_entry(self, tmp_path: Path):
        """find_contradiction_candidates() never raises regardless of store state."""
        with MemoryStore(root=tmp_path, embedder=_unavailable_embedder()) as store:
            # Entry not even in the store
            ghost = MemoryEntry.create(MemoryKind.DECISION, "ghost content", "ghost summary")
            try:
                result = store.find_contradiction_candidates(ghost)
                assert isinstance(result, list)
            except Exception as exc:
                pytest.fail(f"find_contradiction_candidates raised: {exc}")

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_same_kind_filter(self, tmp_path: Path):
        """same_kind=True (default) excludes candidates of different kinds."""
        from flowstate.embeddings import get_embedder

        near_vec = [0.9, 0.1, 0.0, 0.0]

        def embed_fn(texts: list[str]) -> list[list[float]]:
            return [near_vec for _ in texts]

        embedder = get_embedder(embed_fn=embed_fn)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content research", "summary research")
            e2 = MemoryEntry.create(MemoryKind.DECISION, "content decision", "summary decision")
            store.add(e1)
            store.add(e2)

            candidates = store.find_contradiction_candidates(e1, same_kind=True)
            candidate_ids = {c.entry.id for c in candidates}
            assert e2.id not in candidate_ids, "different kind must be excluded with same_kind=True"

    @pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
    def test_same_kind_false_includes_different_kinds(self, tmp_path: Path):
        """same_kind=False includes candidates regardless of kind."""
        from flowstate.embeddings import get_embedder

        near_vec = [0.9, 0.1, 0.0, 0.0]

        def embed_fn(texts: list[str]) -> list[list[float]]:
            return [near_vec for _ in texts]

        embedder = get_embedder(embed_fn=embed_fn)
        with MemoryStore(root=tmp_path, embedder=embedder) as store:
            e1 = MemoryEntry.create(MemoryKind.RESEARCH, "content research", "summary research")
            e2 = MemoryEntry.create(MemoryKind.DECISION, "content decision", "summary decision")
            store.add(e1)
            store.add(e2)

            candidates = store.find_contradiction_candidates(e1, same_kind=False)
            candidate_ids = {c.entry.id for c in candidates}
            assert e2.id in candidate_ids, "different kind must appear with same_kind=False"
