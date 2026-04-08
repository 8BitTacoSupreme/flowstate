"""Tests for flowstate.memory — MemoryStore with SQLite FTS5."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore


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
