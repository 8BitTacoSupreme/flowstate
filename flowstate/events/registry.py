"""Handler registry — maps event types to ordered handler lists."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from flowstate.events.event import Event, EventPriority

logger = logging.getLogger(__name__)


class HandlerRegistry:
    """Thread-safe registry of event handlers keyed by event type."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[EventPriority, Callable]]] = defaultdict(list)
        self._sorted = False

    def register(
        self,
        event_type: str,
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append((priority, handler))
        self._sorted = False
        logger.debug("Registered handler %s for %s (priority=%s)", handler, event_type, priority)

    def register_handler(self, handler: Callable) -> None:
        """Auto-register a decorated handler using its event_types attribute."""
        event_types: list[str] = getattr(handler, "event_types", [])
        priority: EventPriority = getattr(handler, "priority", EventPriority.NORMAL)
        if not event_types:
            raise ValueError(f"Handler {handler} has no event_types attribute — use @handler()")
        for et in event_types:
            self.register(et, handler, priority)

    def get_handlers(self, event_type: str) -> list[Callable]:
        """Return handlers for an event type, sorted by priority (lowest first)."""
        if not self._sorted:
            for et in self._handlers:
                self._handlers[et].sort(key=lambda x: x[0])
            self._sorted = True
        return [h for _, h in self._handlers.get(event_type, [])]

    def get_all_handlers(self, event: Event) -> list[Callable]:
        """Return handlers matching an event, including wildcard '*' handlers."""
        specific = self.get_handlers(event.event_type)
        wildcard = self.get_handlers("*")
        # Merge and re-sort by priority
        all_pairs: list[tuple[EventPriority, Callable]] = []
        for h in specific:
            pri = getattr(h, "priority", EventPriority.NORMAL)
            all_pairs.append((pri, h))
        for h in wildcard:
            pri = getattr(h, "priority", EventPriority.NORMAL)
            all_pairs.append((pri, h))
        all_pairs.sort(key=lambda x: x[0])
        return [h for _, h in all_pairs]

    @property
    def registered_types(self) -> list[str]:
        """Return all event types that have handlers registered."""
        return list(self._handlers.keys())

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()
        self._sorted = False
