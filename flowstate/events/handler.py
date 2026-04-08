"""Event handler protocol and decorator."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

from flowstate.events.event import Event, EventPriority


class EventHandler(Protocol):
    """Protocol for objects that can handle events."""

    event_types: list[str]
    priority: EventPriority

    def __call__(self, event: Event) -> Any: ...


def handler(
    *event_types: str,
    priority: EventPriority = EventPriority.NORMAL,
) -> Callable:
    """Decorator that marks a function as an event handler.

    Usage:
        @handler("pipeline.started", "pipeline.completed")
        def on_pipeline_event(event: Event) -> None:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        fn.event_types = list(event_types)  # type: ignore[attr-defined]
        fn.priority = priority  # type: ignore[attr-defined]

        @functools.wraps(fn)
        def wrapper(event: Event) -> Any:
            return fn(event)

        wrapper.event_types = fn.event_types  # type: ignore[attr-defined]
        wrapper.priority = fn.priority  # type: ignore[attr-defined]
        return wrapper

    return decorator
