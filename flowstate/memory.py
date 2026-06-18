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

from flowstate.embeddings import Embedder, get_embedder

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
    RUN = "run"


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

    # Maximum rows backfilled per open (WR-05: prevents startup hang on large dbs).
    _BACKFILL_BATCH = 500

    def __init__(self, root: Path | None = None, *, embedder: Embedder | None = None) -> None:
        db_path = (root or Path.cwd()) / "memory.db"
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)
        # Embedding provider — use injected instance or create one via factory.
        # Default (embedder=None) produces an Embedder whose available() is False
        # when fastembed is absent, leaving all FTS5 behavior unchanged.
        self._embedder: Embedder = embedder if embedder is not None else get_embedder(root)
        self._vec_ready: bool = False
        # _init_vec uses configured_dim (cheap — no model load), so opening a
        # MemoryStore never downloads the real fastembed model (VEC-03).
        self._init_vec()
        # Backfill is deferred to the first write so that read-only paths
        # (status, count, last_entry_at) do not trigger any embed work.
        self._backfill_pending: bool = self._vec_ready

    # ------------------------------------------------------------------
    # Private vec0 helpers
    # ------------------------------------------------------------------

    def _init_vec(self) -> None:
        """Load sqlite-vec, create memories_vec vec0 table. Never raises.

        Sets self._vec_ready = True on success; False on any failure (sqlite-vec
        absent, vec0 create error, dim mismatch, etc.).

        Security: enable_load_extension(False) is called in a finally block so the
        extension-load surface is ALWAYS re-scoped off, even when sqlite_vec.load()
        raises (T-09-03).

        Startup cost: uses configured_dim (no model load) to size the vec0 table;
        the real model is only constructed on the first actual embed() call.

        Dim mismatch: if the existing memories_vec table was created with a different
        dimension, _vec_ready is set False (FTS5-only mode) rather than silently
        producing a diverged index.
        """
        try:
            self._conn.enable_load_extension(True)
            try:
                import sqlite_vec  # local import — loads only after enable_load_extension(True)

                sqlite_vec.load(self._conn)
            finally:
                # Re-scope off unconditionally — even when sqlite_vec.load() raises.
                self._conn.enable_load_extension(False)
            # Use configured_dim: cheap, does not load the real model.
            dim = self._embedder.configured_dim
            # Detect dim mismatch: if the table already exists with a different
            # dimension, degrade to FTS5-only rather than silently diverging.
            existing = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='memories_vec'"
            ).fetchone()
            if existing is not None:
                import re as _re

                m = _re.search(r"float\[(\d+)\]", existing[0] or "")
                if m and int(m.group(1)) != dim:
                    # Mismatch: mark not-ready so writes stop trying.
                    self._vec_ready = False
                    return
            self._conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0(embedding float[{dim}])"
            )
            self._conn.commit()
            self._vec_ready = True
        except Exception:
            self._vec_ready = False

    def _embed_rowid(self, rowid: int, text: str) -> None:
        """Embed text and upsert a memories_vec row for rowid. Never raises.

        Guarded by _vec_ready and embedder.available(). Deletes any existing
        row first (delete-then-insert = idempotent replace without a REPLACE
        or ON CONFLICT clause, which vec0 may not support).

        On sqlite3.Error (e.g. dim mismatch, disk-full, locked db) _vec_ready
        is flipped False so subsequent writes stop pretending to succeed rather
        than silently diverging memories from memories_vec.  Embedder-level
        failures (returns []) are a silent no-op — FTS5 path is unaffected.
        """
        if not self._vec_ready or not self._embedder.available():
            return
        try:
            import sqlite_vec  # local import — sqlite_vec must be loaded on this conn first

            vec = self._embedder.embed([text])
            if not vec:
                return
            serialized = sqlite_vec.serialize_float32(vec[0])
            self._conn.execute("DELETE FROM memories_vec WHERE rowid=?", (rowid,))
            self._conn.execute(
                "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                (rowid, serialized),
            )
        except sqlite3.Error:
            # Hard DB error: stop vec writes to avoid silent divergence.
            self._vec_ready = False

    def _backfill_vectors(self) -> None:
        """Embed up to _BACKFILL_BATCH un-vectored memories rows. Never raises.

        Guarded by _vec_ready and embedder.available(). Commits once after all
        inserts for efficiency. Idempotent: rows already in memories_vec are
        skipped via the NOT IN subquery.

        The LIMIT cap prevents a startup hang when opening a large db for the
        first time after enabling [semantic] (WR-05).  Any remaining un-vectored
        rows are covered by subsequent opens or explicit calls.
        """
        if not self._vec_ready or not self._embedder.available():
            return
        try:
            rows = self._conn.execute(
                "SELECT rowid, summary, content FROM memories "
                "WHERE rowid NOT IN (SELECT rowid FROM memories_vec) "
                "LIMIT ?",
                (self._BACKFILL_BATCH,),
            ).fetchall()
            if not rows:
                return
            for row in rows:
                text = row["summary"] + "\n" + row["content"]
                self._embed_rowid(row["rowid"], text)
            self._conn.commit()
        except Exception:
            pass

    def _maybe_backfill(self) -> None:
        """Run backfill once on first write; clears the pending flag afterward."""
        if self._backfill_pending:
            self._backfill_pending = False
            self._backfill_vectors()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def add(self, entry: MemoryEntry) -> str:
        self._maybe_backfill()
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
        # Resolve rowid and embed — rowid via SELECT (not cursor.lastrowid) per plan contract
        row = self._conn.execute("SELECT rowid FROM memories WHERE id=?", (entry.id,)).fetchone()
        if row is not None:
            self._embed_rowid(row[0], entry.summary + "\n" + entry.content)
            self._conn.commit()
        return entry.id

    def update(self, entry: MemoryEntry) -> None:
        """Update an existing memory entry by id.

        Issues a single UPDATE memories SET ... WHERE id=? — mirrors the column
        list of add(). The memories_au AFTER UPDATE trigger keeps FTS5 in sync
        automatically; no manual FTS writes are needed here.
        A missing id (zero rows matched) is a silent no-op; it does not raise.
        """
        self._maybe_backfill()
        self._conn.execute(
            """UPDATE memories
               SET kind=?, content=?, summary=?, source=?, tags=?, metadata=?, created_at=?, run_id=?
               WHERE id=?""",
            (
                entry.kind.value,
                entry.content,
                entry.summary,
                entry.source,
                json.dumps(entry.tags),
                json.dumps(entry.metadata),
                entry.created_at.isoformat(),
                entry.run_id,
                entry.id,
            ),
        )
        self._conn.commit()
        # Re-embed: resolve rowid (row may not exist if id was not in db)
        row = self._conn.execute("SELECT rowid FROM memories WHERE id=?", (entry.id,)).fetchone()
        if row is not None:
            self._embed_rowid(row[0], entry.summary + "\n" + entry.content)
            self._conn.commit()

    def add_many(self, entries: list[MemoryEntry]) -> list[str]:
        self._maybe_backfill()
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
        # Embed per entry inside a savepoint so vec writes are all-or-nothing
        # for this call — a DB error rolls back all vec rows inserted here
        # rather than leaving memories and memories_vec in a partially-diverged
        # state (WR-04).  _embed_rowid swallows embedder failures silently;
        # the savepoint guards against hard sqlite3.Error escapes.
        if self._vec_ready and self._embedder.available():
            try:
                self._conn.execute("SAVEPOINT add_many_vec")
                for entry in entries:
                    row = self._conn.execute(
                        "SELECT rowid FROM memories WHERE id=?", (entry.id,)
                    ).fetchone()
                    if row is not None:
                        # Call embed directly (bypass _embed_rowid's per-row swallow)
                        # so a DB error escapes to the outer except.
                        import sqlite_vec  # local import

                        vec = self._embedder.embed([entry.summary + "\n" + entry.content])
                        if vec:
                            serialized = sqlite_vec.serialize_float32(vec[0])
                            self._conn.execute("DELETE FROM memories_vec WHERE rowid=?", (row[0],))
                            self._conn.execute(
                                "INSERT INTO memories_vec(rowid, embedding) VALUES (?, ?)",
                                (row[0], serialized),
                            )
                self._conn.execute("RELEASE SAVEPOINT add_many_vec")
                self._conn.commit()
            except Exception:
                # Roll back all vec inserts for this call — FTS5/memories are unaffected.
                try:
                    self._conn.execute("ROLLBACK TO SAVEPOINT add_many_vec")
                    self._conn.execute("RELEASE SAVEPOINT add_many_vec")
                except Exception:
                    pass
                self._vec_ready = False
        return ids

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Escape a raw string for FTS5 MATCH.

        FTS5 interprets bare words as column names if they match a column,
        and operators like AND/OR/NOT/NEAR have special meaning.  Wrapping
        each token in double-quotes forces literal matching.
        """
        tokens = query.split()
        if not tokens:
            return query
        return " ".join(f'"{t}"' for t in tokens)

    def search(
        self,
        query: str,
        *,
        kind: MemoryKind | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not query.strip():
            return []

        safe_query = self._sanitize_fts_query(query)

        if kind is not None:
            rows = self._conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                     AND m.kind = ?
                   ORDER BY rank
                   LIMIT ?""",
                (safe_query, kind.value, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (safe_query, limit),
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

    def get_gotchas(self) -> list[MemoryEntry]:
        """Return ALL gotcha-tagged INSIGHT entries ordered by created_at DESC.

        Uses a SQL LIKE filter on the tags column so the result is not limited
        by the arbitrary limit budget shared with non-gotcha INSIGHT entries.
        The LIKE pattern is parameterized — no injection risk.
        """
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE kind = ? AND tags LIKE ? ORDER BY created_at DESC",
            (MemoryKind.INSIGHT.value, '%"gotcha"%'),
        ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def delete(self, memory_id: str) -> None:
        """Delete a memory entry by id. FTS index updated via memories_ad trigger."""
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()

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

    def last_entry_at(self) -> datetime | None:
        """Return the created_at timestamp of the most recently inserted memory, or None.

        Public helper so callers don't reach into the private `_conn` attribute.
        Used by the status_markdown renderer.
        """
        row = self._conn.execute(
            "SELECT created_at FROM memories ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        raw = row["created_at"] if hasattr(row, "keys") else row[0]
        try:
            return datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None

    def count(self, kind: MemoryKind | None = None, *, run_id: str | None = None) -> int:
        if kind is not None and run_id is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE kind = ? AND run_id = ?",
                (kind.value, run_id),
            ).fetchone()
        elif kind is not None:
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
