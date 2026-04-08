"""Persistent memory store backed by SQLite FTS5.

Provides cross-run continuity for FlowState pipelines. Research findings,
strategy decisions, and failure context are stored and searchable via
full-text search with BM25 ranking.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO schema_version (version) VALUES (1);

CREATE TABLE IF NOT EXISTS memories (
    rowid INTEGER PRIMARY KEY,
    id TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_run_id ON memories(run_id);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    summary,
    content,
    tags,
    content=memories,
    content_rowid=rowid,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, summary, content, tags)
    VALUES (new.rowid, new.summary, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, summary, content, tags)
    VALUES ('delete', old.rowid, old.summary, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, summary, content, tags)
    VALUES ('delete', old.rowid, old.summary, old.content, old.tags);
    INSERT INTO memories_fts(rowid, summary, content, tags)
    VALUES (new.rowid, new.summary, new.content, new.tags);
END;
"""


class MemoryKind(StrEnum):
    RESEARCH = "research"
    STRATEGY = "strategy"
    DECISION = "decision"
    TOOL_RUN = "tool_run"
    INSIGHT = "insight"


@dataclass
class MemoryEntry:
    id: str
    kind: MemoryKind
    content: str
    summary: str
    source: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    run_id: str = ""

    @classmethod
    def create(
        cls,
        kind: MemoryKind,
        content: str,
        summary: str,
        *,
        source: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: str = "",
    ) -> MemoryEntry:
        return cls(
            id=uuid4().hex[:12],
            kind=kind,
            content=content,
            summary=summary,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
            run_id=run_id,
        )


@dataclass
class SearchResult:
    entry: MemoryEntry
    score: float


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        kind=MemoryKind(row["kind"]),
        content=row["content"],
        summary=row["summary"],
        source=row["source"],
        tags=json.loads(row["tags"]),
        metadata=json.loads(row["metadata"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        run_id=row["run_id"],
    )


class MemoryStore:
    """SQLite-backed memory store with FTS5 full-text search."""

    def __init__(self, root: Path | None = None) -> None:
        db_path = (root or Path.cwd()) / "memory.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def add(self, entry: MemoryEntry) -> str:
        self._conn.execute(
            """INSERT INTO memories (id, kind, content, summary, source, tags, metadata, created_at, run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.kind.value,
                entry.content,
                entry.summary,
                entry.source,
                json.dumps(entry.tags),
                json.dumps(entry.metadata),
                entry.created_at.isoformat(),
                entry.run_id,
            ),
        )
        self._conn.commit()
        return entry.id

    def add_many(self, entries: list[MemoryEntry]) -> list[str]:
        ids = []
        for entry in entries:
            self._conn.execute(
                """INSERT INTO memories (id, kind, content, summary, source, tags, metadata, created_at, run_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.kind.value,
                    entry.content,
                    entry.summary,
                    entry.source,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                    entry.created_at.isoformat(),
                    entry.run_id,
                ),
            )
            ids.append(entry.id)
        self._conn.commit()
        return ids

    def search(
        self,
        query: str,
        *,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not query.strip():
            return []

        if kind is not None:
            rows = self._conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                     AND m.kind = ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, kind.value, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            ).fetchall()

        return [SearchResult(entry=_row_to_entry(row), score=abs(row["rank"])) for row in rows]

    def get(self, memory_id: str) -> MemoryEntry | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def get_by_kind(self, kind: MemoryKind, *, limit: int = 20) -> list[MemoryEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
            (kind.value, limit),
        ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def get_context(self, query: str, *, max_tokens: int = 2000) -> str:
        """Return markdown-formatted context for prompt injection.

        Searches for relevant memories and formats them as a markdown section.
        Approximate token budget via character count (1 token ~ 4 chars).
        """
        results = self.search(query, limit=10)
        if not results:
            return ""

        char_budget = max_tokens * 4
        lines = ["## Prior Knowledge\n"]
        used = len(lines[0])

        for sr in results:
            entry = sr.entry
            header = f"### {entry.summary} ({entry.kind.value})\n"
            body = entry.content.strip()
            block = header + body + "\n\n"

            if used + len(block) > char_budget:
                remaining = char_budget - used - len(header) - 10
                if remaining > 100:
                    lines.append(header + body[:remaining] + "...\n\n")
                break

            lines.append(block)
            used += len(block)

        return "".join(lines)

    def count(self, kind: MemoryKind | None = None) -> int:
        if kind is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE kind = ?",
                (kind.value,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        return row["cnt"]

    def clear(self) -> int:
        count = self.count()
        self._conn.executescript("DELETE FROM memories; DELETE FROM memories_fts;")
        return count
