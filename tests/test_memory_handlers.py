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

        # TOOL_RUN entry count is unchanged (existing behavior preserved)
        entries = mem_store.get_by_kind(MemoryKind.TOOL_RUN)
        assert len(entries) == 1
        assert "timeout" in entries[0].content
        assert entries[0].run_id == "test-run"
        assert "failure" in entries[0].tags

    def test_step_failed_also_captures_executor_gotcha(self, wired_bus, mem_store, tmp_path):
        """Firing step.failed stores TOOL_RUN AND an INSIGHT gotcha with source=executor."""
        event = StepFailed(
            payload={"tool": "strategy", "error": "bridge timeout"},
            source="test",
        )
        wired_bus.emit(event)

        # Existing TOOL_RUN entry still present
        tool_run_entries = mem_store.get_by_kind(MemoryKind.TOOL_RUN)
        assert len(tool_run_entries) == 1

        # New INSIGHT gotcha also captured
        insight_entries = mem_store.get_by_kind(MemoryKind.INSIGHT)
        gotcha_entries = [e for e in insight_entries if "gotcha" in e.tags]
        assert len(gotcha_entries) == 1
        assert "executor" in gotcha_entries[0].tags
        assert gotcha_entries[0].metadata.get("severity") == "error"
        assert gotcha_entries[0].run_id == "test-run"

    def test_step_failed_gotcha_dedup(self, wired_bus, mem_store, tmp_path):
        """Two step.failed events with the same tool+error produce ONE gotcha (count=2)."""
        event = StepFailed(
            payload={"tool": "research", "error": "repeated failure"},
            source="test",
        )
        wired_bus.emit(event)
        wired_bus.emit(event)

        # Two TOOL_RUN entries (existing behavior unchanged)
        assert len(mem_store.get_by_kind(MemoryKind.TOOL_RUN)) == 2

        # One deduplicated gotcha with count=2
        insight_entries = mem_store.get_by_kind(MemoryKind.INSIGHT)
        gotcha_entries = [e for e in insight_entries if "gotcha" in e.tags]
        assert len(gotcha_entries) == 1
        assert gotcha_entries[0].metadata.get("count") == 2

    def test_step_failed_gotcha_failure_is_nonfatal(self, mem_store, tmp_path, monkeypatch):
        """If capture_gotcha raises, the TOOL_RUN store still completes."""
        from unittest.mock import patch

        bus = EventBus(keep_history=True)
        handlers = create_memory_handlers(mem_store, tmp_path, run_id="safe-run")
        for h in handlers:
            bus.register(h)

        # Patch capture_gotcha to raise
        with patch("flowstate.gotchas.capture_gotcha", side_effect=RuntimeError("boom")):
            event = StepFailed(
                payload={"tool": "gsd", "error": "exploded"},
                source="test",
            )
            bus.emit(event)

        # TOOL_RUN entry still landed
        assert mem_store.count(MemoryKind.TOOL_RUN) == 1


class TestMemoryHandlersProfileGating:
    """HOOK-01 / HOOK-02 integration: memory handlers tagged 'minimal'."""

    def test_handlers_tagged_minimal(self, tmp_path):
        with MemoryStore(root=tmp_path) as store:
            handlers = create_memory_handlers(store, tmp_path)
        assert len(handlers) == 2
        for h in handlers:
            assert h.profile == "minimal"

    def test_register_with_minimal_env_succeeds(self, tmp_path, monkeypatch):
        from flowstate.events.registry import HandlerRegistry

        monkeypatch.setenv("FLOWSTATE_HANDLERS", "minimal")
        monkeypatch.delenv("FLOWSTATE_DISABLED_HANDLERS", raising=False)
        reg = HandlerRegistry()
        with MemoryStore(root=tmp_path) as store:
            handlers = create_memory_handlers(store, tmp_path)
        for h in handlers:
            assert reg.register_handler(h) is True

    def test_disabled_handler_skipped(self, tmp_path, monkeypatch):
        from flowstate.events.registry import HandlerRegistry

        monkeypatch.setenv("FLOWSTATE_HANDLERS", "standard")
        monkeypatch.setenv("FLOWSTATE_DISABLED_HANDLERS", "on_step_failed")
        reg = HandlerRegistry()
        with MemoryStore(root=tmp_path) as store:
            handlers = create_memory_handlers(store, tmp_path)
        results = {h.__name__: reg.register_handler(h) for h in handlers}
        assert results["on_step_completed"] is True
        assert results["on_step_failed"] is False
