"""Event handlers that auto-store memories when pipeline steps complete.

Listens for StepCompleted and StepFailed events, reads artifact files,
and stores content as searchable memory entries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from flowstate.events.event import EventPriority
from flowstate.events.handler import handler
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

if TYPE_CHECKING:
    from flowstate.events.event import Event

MAX_ARTIFACT_CHARS = 8000
MAX_SECTION_CHARS = 1500

TOOL_TO_KIND = {
    "research": MemoryKind.RESEARCH,
    "strategy": MemoryKind.STRATEGY,
    "gsd": MemoryKind.DECISION,
    "discipline": MemoryKind.TOOL_RUN,
}


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown by ## headings into (heading, body) tuples."""
    parts = re.split(r"^(## .+)$", text, flags=re.MULTILINE)

    sections = []
    # parts[0] is text before first heading (if any)
    if parts[0].strip():
        sections.append(("Overview", parts[0].strip()))

    # Remaining parts alternate: heading, body, heading, body...
    for i in range(1, len(parts), 2):
        heading = parts[i].lstrip("# ").strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((heading, body))

    return sections


def create_memory_handlers(store: MemoryStore, root: Path, run_id: str = "") -> list:
    """Create event handlers that store pipeline results as memories.

    Returns a list of decorated handler functions ready for bus.register().
    """

    @handler("step.completed", priority=EventPriority.AUDIT)
    def on_step_completed(event: Event) -> None:
        tool_name = event.payload.get("tool", "")
        artifacts = event.payload.get("artifacts", [])
        kind = TOOL_TO_KIND.get(tool_name, MemoryKind.INSIGHT)

        for artifact_path in artifacts:
            path = Path(artifact_path)
            if not path.is_absolute():
                path = root / path

            if not path.exists() or not path.is_file():
                continue

            content = path.read_text(errors="replace")[:MAX_ARTIFACT_CHARS]
            sections = _split_sections(content)

            if not sections:
                store.add(
                    MemoryEntry.create(
                        kind,
                        content[:MAX_SECTION_CHARS],
                        f"{tool_name}: {path.name}",
                        source=str(artifact_path),
                        tags=[tool_name],
                        run_id=run_id,
                    )
                )
                continue

            entries = []
            for heading, body in sections:
                entries.append(
                    MemoryEntry.create(
                        kind,
                        body[:MAX_SECTION_CHARS],
                        f"{tool_name}: {heading}",
                        source=str(artifact_path),
                        tags=[tool_name, heading.lower()],
                        run_id=run_id,
                    )
                )
            store.add_many(entries)

    @handler("step.failed", priority=EventPriority.AUDIT)
    def on_step_failed(event: Event) -> None:
        tool_name = event.payload.get("tool", "")
        error = event.payload.get("error", "unknown error")

        store.add(
            MemoryEntry.create(
                MemoryKind.TOOL_RUN,
                f"Tool '{tool_name}' failed: {error}",
                f"{tool_name} failure",
                source=tool_name,
                tags=[tool_name, "failure"],
                run_id=run_id,
            )
        )

    return [on_step_completed, on_step_failed]
