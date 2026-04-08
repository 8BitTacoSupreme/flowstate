"""Event base class and priority definitions."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventPriority(IntEnum):
    """Handler execution priority — lower runs first."""

    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 90
    AUDIT = 100


class Event(BaseModel):
    """Base event carrying a typed payload through the bus."""

    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}

    def with_metadata(self, **kwargs: Any) -> Event:
        """Return a copy with additional metadata merged in."""
        merged = {**self.metadata, **kwargs}
        return self.model_copy(update={"metadata": merged})


# --- Concrete domain events ---


class PipelineStarted(Event):
    """Emitted when the GrandSlam pipeline begins."""

    event_type: str = "pipeline.started"


class PipelineCompleted(Event):
    """Emitted when the pipeline finishes (success or partial)."""

    event_type: str = "pipeline.completed"


class StepStarted(Event):
    """Emitted when an individual pipeline step starts."""

    event_type: str = "step.started"


class StepCompleted(Event):
    """Emitted when an individual pipeline step finishes."""

    event_type: str = "step.completed"


class StepFailed(Event):
    """Emitted when an individual pipeline step fails."""

    event_type: str = "step.failed"


class StateChanged(Event):
    """Emitted when FlowState model is persisted."""

    event_type: str = "state.changed"
