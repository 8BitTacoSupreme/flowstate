"""Tests for flowstate.memory_handlers — EventBus integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowstate.events.bus import EventBus
from flowstate.events.event import StepCompleted, StepFailed
from flowstate.memory import MemoryKind, MemoryStore
from flowstate.memory_handlers import create_memory_handlers


@pytest.fixture()
def mem_store(tmp_path: Path) -> MemoryStore:
    with MemoryStore(root=tmp_path) as s:
        yield s


@pytest.fixture()
def wired_bus(mem_store: MemoryStore, tmp_path: Path) -> EventBus:
    bus = EventBus(keep_history=True)
    handlers = create_memory_handlers(mem_store, tmp_path, run_id="test-run")
    for h in handlers:
        bus.register(h)
    return bus


class TestStepCompleted:
    def test_stores_artifact_sections(self, wired_bus, mem_store, tmp_path):
        artifact = tmp_path / "research" / "report.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            "# Research Report\n\n"
            "## Kafka Streams\n\n"
            "Kafka Streams is a client library for building stream processing apps.\n\n"
            "## Flink SQL\n\n"
            "Flink SQL provides declarative SQL queries over streaming data.\n"
        )

        event = StepCompleted(
            payload={
                "tool": "research",
                "artifacts": [str(artifact)],
            },
            source="test",
        )
        wired_bus.emit(event)

        assert mem_store.count() == 3  # Overview + 2 H2 sections
        entries = mem_store.get_by_kind(MemoryKind.RESEARCH)
        assert len(entries) == 3
        summaries = {e.summary for e in entries}
        assert "research: Kafka Streams" in summaries
        assert "research: Flink SQL" in summaries

    def test_stores_with_run_id(self, wired_bus, mem_store, tmp_path):
        artifact = tmp_path / "report.md"
        artifact.write_text("## Section\n\nContent here.\n")

        event = StepCompleted(
            payload={"tool": "research", "artifacts": [str(artifact)]},
            source="test",
        )
        wired_bus.emit(event)

        entries = mem_store.get_by_kind(MemoryKind.RESEARCH)
        assert all(e.run_id == "test-run" for e in entries)

    def test_skips_missing_artifact(self, wired_bus, mem_store):
        event = StepCompleted(
            payload={
                "tool": "research",
                "artifacts": ["/nonexistent/file.md"],
            },
            source="test",
        )
        wired_bus.emit(event)
        assert mem_store.count() == 0

    def test_handles_no_headings(self, wired_bus, mem_store, tmp_path):
        artifact = tmp_path / "plain.md"
        artifact.write_text("Just plain text content without any headings.\n")

        event = StepCompleted(
            payload={"tool": "strategy", "artifacts": [str(artifact)]},
            source="test",
        )
        wired_bus.emit(event)

        assert mem_store.count() == 1
        entries = mem_store.get_by_kind(MemoryKind.STRATEGY)
        assert entries[0].summary == "strategy: Overview"

    def test_relative_artifact_path(self, wired_bus, mem_store, tmp_path):
        artifact = tmp_path / "research" / "report.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("## Topic\n\nRelative path content.\n")

        event = StepCompleted(
            payload={
                "tool": "research",
                "artifacts": ["research/report.md"],
            },
            source="test",
        )
        wired_bus.emit(event)

        assert mem_store.count() == 1


class TestStepFailed:
    def test_stores_failure(self, wired_bus, mem_store):
        event = StepFailed(
            payload={
                "tool": "research",
                "error": "timeout after 60s",
            },
            source="test",
        )
        wired_bus.emit(event)

        assert mem_store.count() == 1
        entries = mem_store.get_by_kind(MemoryKind.TOOL_RUN)
        assert len(entries) == 1
        assert "timeout" in entries[0].content
        assert entries[0].run_id == "test-run"
        assert "failure" in entries[0].tags
