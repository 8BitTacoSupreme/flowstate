"""Event handler protocol and decorator."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

from flowstate.events.event import Event, EventPriority

VALID_PROFILES = ("minimal", "standard", "strict")


class EventHandler(Protocol):
    """Protocol for objects that can handle events."""

    event_types: list[str]
    priority: EventPriority
    profile: str

    def __call__(self, event: Event) -> Any: ...


def handler(
    *event_types: str,
    priority: EventPriority = EventPriority.NORMAL,
    profile: Literal["minimal", "standard", "strict"] = "standard",
) -> Callable:
    """Decorator that marks a function as an event handler.

    Args:
        *event_types: One or more event type strings to subscribe to.
        priority: Dispatch order (lower = earlier).
        profile: Gating profile. Handlers with profile stricter than the
            FLOWSTATE_HANDLERS env var setting are skipped at register time.
            Order: minimal < standard < strict. Default is "standard".

    Usage:
        @handler("pipeline.started", profile="minimal")
        def on_started(event: Event) -> None: ...
    """
    if profile not in VALID_PROFILES:
        raise ValueError(f"Invalid profile {profile!r}. Must be one of {VALID_PROFILES}.")

    def decorator(fn: Callable) -> Callable:
        fn.event_types = list(event_types)  # type: ignore[attr-defined]
        fn.priority = priority  # type: ignore[attr-defined]
        fn.profile = profile  # type: ignore[attr-defined]

        @functools.wraps(fn)
        def wrapper(event: Event) -> Any:
            return fn(event)

        wrapper.event_types = fn.event_types  # type: ignore[attr-defined]
        wrapper.priority = fn.priority  # type: ignore[attr-defined]
        wrapper.profile = fn.profile  # type: ignore[attr-defined]
        return wrapper

    return decorator
