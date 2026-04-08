"""Tests for the event-driven infrastructure."""

from __future__ import annotations

import pytest

from flowstate.events.bus import EventBus
from flowstate.events.event import (
    Event,
    EventPriority,
    PipelineCompleted,
    PipelineStarted,
    StateChanged,
    StepCompleted,
    StepFailed,
    StepStarted,
)
from flowstate.events.handler import handler
from flowstate.events.registry import HandlerRegistry

# ── Event model tests ────────────────────────────────────────────────


class TestEvent:
    def test_event_has_id_and_timestamp(self, sample_event: Event):
        assert len(sample_event.event_id) == 12
        assert sample_event.timestamp is not None

    def test_event_is_frozen(self, sample_event: Event):
        with pytest.raises(Exception):  # noqa: B017
            sample_event.event_type = "changed"

    def test_with_metadata_returns_copy(self, sample_event: Event):
        updated = sample_event.with_metadata(trace_id="abc")
        assert updated.metadata["trace_id"] == "abc"
        assert "trace_id" not in sample_event.metadata  # original unchanged

    def test_domain_events_have_correct_types(self):
        assert PipelineStarted().event_type == "pipeline.started"
        assert PipelineCompleted().event_type == "pipeline.completed"
        assert StepStarted().event_type == "step.started"
        assert StepCompleted().event_type == "step.completed"
        assert StepFailed().event_type == "step.failed"
        assert StateChanged().event_type == "state.changed"


# ── Handler decorator tests ─────────────────────────────────────────


class TestHandlerDecorator:
    def test_decorator_sets_event_types(self):
        @handler("step.started", "step.completed")
        def on_step(event: Event) -> None:
            pass

        assert on_step.event_types == ["step.started", "step.completed"]

    def test_decorator_sets_priority(self):
        @handler("test", priority=EventPriority.HIGH)
        def on_test(event: Event) -> None:
            pass

        assert on_test.priority == EventPriority.HIGH

    def test_decorator_defaults_to_normal(self):
        @handler("test")
        def on_test(event: Event) -> None:
            pass

        assert on_test.priority == EventPriority.NORMAL

    def test_decorated_function_is_callable(self, sample_event: Event):
        results = []

        @handler("test.event")
        def on_test(event: Event) -> str:
            results.append(event.event_type)
            return "handled"

        assert on_test(sample_event) == "handled"
        assert results == ["test.event"]


# ── Registry tests ───────────────────────────────────────────────────


class TestHandlerRegistry:
    def test_register_and_retrieve(self):
        reg = HandlerRegistry()
        called = []
        reg.register("test.event", lambda e: called.append(e))
        handlers = reg.get_handlers("test.event")
        assert len(handlers) == 1

    def test_priority_ordering(self):
        reg = HandlerRegistry()
        order = []
        reg.register("test", lambda e: order.append("low"), EventPriority.LOW)
        reg.register("test", lambda e: order.append("high"), EventPriority.HIGH)
        reg.register("test", lambda e: order.append("critical"), EventPriority.CRITICAL)

        for h in reg.get_handlers("test"):
            h(None)

        assert order == ["critical", "high", "low"]

    def test_register_decorated_handler(self):
        reg = HandlerRegistry()

        @handler("a", "b", priority=EventPriority.HIGH)
        def multi_handler(event: Event) -> None:
            pass

        reg.register_handler(multi_handler)
        assert len(reg.get_handlers("a")) == 1
        assert len(reg.get_handlers("b")) == 1

    def test_register_handler_without_decorator_raises(self):
        reg = HandlerRegistry()
        with pytest.raises(ValueError, match="no event_types"):
            reg.register_handler(lambda e: None)

    def test_registered_types(self):
        reg = HandlerRegistry()
        reg.register("alpha", lambda e: None)
        reg.register("beta", lambda e: None)
        assert sorted(reg.registered_types) == ["alpha", "beta"]

    def test_clear(self):
        reg = HandlerRegistry()
        reg.register("test", lambda e: None)
        reg.clear()
        assert reg.get_handlers("test") == []

    def test_wildcard_handlers(self):
        reg = HandlerRegistry()
        calls = []
        reg.register("*", lambda e: calls.append("wildcard"))
        reg.register("specific", lambda e: calls.append("specific"))

        event = Event(event_type="specific")
        for h in reg.get_all_handlers(event):
            h(event)

        assert "wildcard" in calls
        assert "specific" in calls


# ── EventBus tests ───────────────────────────────────────────────────


class TestEventBus:
    def test_emit_dispatches_to_handler(self, bus: EventBus, sample_event: Event):
        received = []
        bus.on("test.event", lambda e: received.append(e.event_type))
        bus.emit(sample_event)
        assert received == ["test.event"]

    def test_emit_returns_results(self, bus: EventBus, pipeline_started: PipelineStarted):
        bus.on("pipeline.started", lambda e: "ack")
        results = bus.emit(pipeline_started)
        assert results == ["ack"]

    def test_history_tracking(self, bus: EventBus, sample_event: Event):
        bus.emit(sample_event)
        assert len(bus.history) == 1
        assert bus.history[0].event_type == "test.event"

    def test_history_disabled_by_default(self, sample_event: Event):
        bus = EventBus(keep_history=False)
        bus.emit(sample_event)
        assert len(bus.history) == 0

    def test_error_isolation(self, bus: EventBus, sample_event: Event):
        """One handler failing should not prevent others from running."""
        results = []
        bus.on("test.event", lambda e: 1 / 0)  # will raise
        bus.on("test.event", lambda e: results.append("ok"))
        bus.emit(sample_event)
        assert results == ["ok"]

    def test_error_handler_called(self, bus: EventBus, sample_event: Event):
        errors = []
        bus.on_error(lambda e, exc: errors.append(str(exc)))
        bus.on("test.event", lambda e: 1 / 0)
        bus.emit(sample_event)
        assert len(errors) == 1
        assert "division by zero" in errors[0]

    def test_wildcard_handler(self, bus: EventBus):
        all_events = []
        bus.on("*", lambda e: all_events.append(e.event_type))
        bus.emit(PipelineStarted(source="test"))
        bus.emit(StepStarted(source="test"))
        assert all_events == ["pipeline.started", "step.started"]

    def test_register_decorated_handler(self, bus: EventBus):
        calls = []

        @handler("step.completed", "step.failed")
        def on_step_done(event: Event) -> None:
            calls.append(event.event_type)

        bus.register(on_step_done)
        bus.emit(StepCompleted(source="test"))
        bus.emit(StepFailed(source="test"))
        assert calls == ["step.completed", "step.failed"]

    def test_clear(self, bus: EventBus, sample_event: Event):
        bus.on("test.event", lambda e: None)
        bus.emit(sample_event)
        bus.clear()
        assert len(bus.history) == 0
        assert len(bus.registered_types) == 0

    def test_priority_ordering_in_bus(self, bus: EventBus):
        order = []
        bus.on("test", lambda e: order.append("normal"), EventPriority.NORMAL)
        bus.on("test", lambda e: order.append("critical"), EventPriority.CRITICAL)
        bus.on("test", lambda e: order.append("audit"), EventPriority.AUDIT)
        bus.emit(Event(event_type="test"))
        assert order == ["critical", "normal", "audit"]

    def test_multiple_events_full_flow(self, bus: EventBus):
        """Simulate a mini pipeline flow through events."""
        log: list[str] = []

        @handler("pipeline.started", priority=EventPriority.HIGH)
        def on_start(event: Event) -> None:
            log.append("pipeline:start")

        @handler("step.started", "step.completed")
        def on_step(event: Event) -> None:
            tool = event.payload.get("tool", "unknown")
            log.append(f"step:{event.event_type.split('.')[-1]}:{tool}")

        @handler("pipeline.completed", priority=EventPriority.LOW)
        def on_done(event: Event) -> None:
            log.append("pipeline:done")

        bus.register(on_start)
        bus.register(on_step)
        bus.register(on_done)

        bus.emit(PipelineStarted(source="orchestrator"))
        bus.emit(StepStarted(payload={"tool": "autoresearch"}, source="orchestrator"))
        bus.emit(StepCompleted(payload={"tool": "autoresearch"}, source="orchestrator"))
        bus.emit(PipelineCompleted(source="orchestrator"))

        assert log == [
            "pipeline:start",
            "step:started:autoresearch",
            "step:completed:autoresearch",
            "pipeline:done",
        ]
