"""Handler registry — maps event types to ordered handler lists."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from flowstate.events.event import Event, EventPriority

logger = logging.getLogger(__name__)

_PROFILE_ORDER = {"minimal": 0, "standard": 1, "strict": 2}
_DEFAULT_PROFILE = "standard"


def _current_profile() -> int:
    """Return the rank of the current FLOWSTATE_HANDLERS env profile.

    Reads os.environ on every call (no module-level caching) so tests can
    monkeypatch the env var freely. Unset or unrecognized values fall back
    to 'standard'.
    """
    raw = os.environ.get("FLOWSTATE_HANDLERS", _DEFAULT_PROFILE).lower().strip()
    return _PROFILE_ORDER.get(raw, _PROFILE_ORDER[_DEFAULT_PROFILE])


def _disabled_names() -> set[str]:
    """Parse FLOWSTATE_DISABLED_HANDLERS env var into a set of handler names.

    Per-call lookup (no caching). Comma-separated; whitespace around commas
    tolerated; empty strings ignored.
    """
    raw = os.environ.get("FLOWSTATE_DISABLED_HANDLERS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


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
        """Register a handler for a specific event type (unconditional)."""
        self._handlers[event_type].append((priority, handler))
        self._sorted = False
        logger.debug("Registered handler %s for %s (priority=%s)", handler, event_type, priority)

    def register_handler(self, handler: Callable) -> bool:
        """Auto-register a decorated handler; honor profile + disabled gating.

        Returns True if the handler was registered, False if it was skipped
        because of profile rank or FLOWSTATE_DISABLED_HANDLERS.
        """
        event_types: list[str] = getattr(handler, "event_types", [])
        priority: EventPriority = getattr(handler, "priority", EventPriority.NORMAL)
        handler_profile: str = getattr(handler, "profile", _DEFAULT_PROFILE)
        handler_name: str = getattr(handler, "__name__", repr(handler))

        if not event_types:
            raise ValueError(f"Handler {handler} has no event_types attribute — use @handler()")

        # Disabled-names takes precedence over profile
        if handler_name in _disabled_names():
            logger.info(
                "Skipping handler %s — listed in FLOWSTATE_DISABLED_HANDLERS",
                handler_name,
            )
            return False

        handler_rank = _PROFILE_ORDER.get(handler_profile, _PROFILE_ORDER[_DEFAULT_PROFILE])
        if handler_rank > _current_profile():
            logger.info(
                "Skipping handler %s (profile=%s) — stricter than current FLOWSTATE_HANDLERS profile",
                handler_name,
                handler_profile,
            )
            return False

        for et in event_types:
            self.register(et, handler, priority)
        return True

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
