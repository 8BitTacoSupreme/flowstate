"""Shared test fixtures for FlowState."""

from __future__ import annotations

import pytest

from flowstate.events.bus import EventBus
from flowstate.events.event import (
    Event,
    PipelineStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
)
from flowstate.state import FlowStateModel


@pytest.fixture()
def bus() -> EventBus:
    """Fresh EventBus with history enabled."""
    return EventBus(keep_history=True)


@pytest.fixture()
def state() -> FlowStateModel:
    """Default FlowStateModel for testing."""
    return FlowStateModel()


@pytest.fixture()
def sample_event() -> Event:
    """A generic test event."""
    return Event(event_type="test.event", payload={"key": "value"}, source="test")


@pytest.fixture()
def pipeline_started() -> PipelineStarted:
    return PipelineStarted(source="test-orchestrator")


@pytest.fixture()
def step_started() -> StepStarted:
    return StepStarted(payload={"tool": "research", "step": 1}, source="test")


@pytest.fixture()
def step_completed() -> StepCompleted:
    return StepCompleted(
        payload={"tool": "research", "step": 1, "artifacts": ["report.md"]},
        source="test",
    )


@pytest.fixture()
def step_failed() -> StepFailed:
    return StepFailed(
        payload={"tool": "gsd", "step": 3, "error": "command not found"},
        source="test",
    )
