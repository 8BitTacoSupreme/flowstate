"""EventBus — central dispatch for the event-driven architecture."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from flowstate.events.event import Event, EventPriority
from flowstate.events.registry import HandlerRegistry

logger = logging.getLogger(__name__)


class EventBus:
    """Synchronous event bus with priority-ordered dispatch.

    Usage:
        bus = EventBus()
        bus.on("pipeline.started", my_handler)
        bus.emit(PipelineStarted(source="orchestrator"))

    Supports:
    - Priority-ordered handler execution
    - Wildcard ("*") handlers that receive all events
    - Event history for debugging / replay
    - Error isolation (one handler failure doesn't stop others)
    """

    def __init__(self, *, keep_history: bool = False) -> None:
        self._registry = HandlerRegistry()
        self._keep_history = keep_history
        self._history: list[Event] = []
        self._error_handlers: list[Callable[[Event, Exception], None]] = []

    # --- Registration ---

    def on(
        self,
        event_type: str,
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
    ) -> None:
        """Register a handler for a specific event type."""
        self._registry.register(event_type, handler, priority)

    def register(self, handler: Callable) -> None:
        """Auto-register a @handler-decorated callable."""
        self._registry.register_handler(handler)

    def on_error(self, handler: Callable[[Event, Exception], None]) -> None:
        """Register an error handler for dispatch failures."""
        self._error_handlers.append(handler)

    # --- Dispatch ---

    def emit(self, event: Event) -> list[Any]:
        """Dispatch an event to all matching handlers, returning results.

        Handlers are called in priority order.  Exceptions are caught and
        forwarded to error handlers so one broken handler cannot block others.
        """
        if self._keep_history:
            self._history.append(event)

        handlers = self._registry.get_all_handlers(event)
        results: list[Any] = []

        for h in handlers:
            try:
                result = h(event)
                results.append(result)
            except Exception as exc:
                logger.exception("Handler %s failed for %s", h, event.event_type)
                self._dispatch_error(event, exc)
                results.append(None)

        return results

    # --- Introspection ---

    @property
    def history(self) -> list[Event]:
        """Return list of emitted events (only if keep_history=True)."""
        return list(self._history)

    @property
    def registered_types(self) -> list[str]:
        """Return event types that have handlers."""
        return self._registry.registered_types

    def clear(self) -> None:
        """Remove all handlers and history."""
        self._registry.clear()
        self._history.clear()
        self._error_handlers.clear()

    # --- Internals ---

    def _dispatch_error(self, event: Event, exc: Exception) -> None:
        for eh in self._error_handlers:
            try:
                eh(event, exc)
            except Exception:
                logger.exception("Error handler itself failed")
