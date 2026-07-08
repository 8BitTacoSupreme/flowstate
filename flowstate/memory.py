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

# Default k for semantic KNN retrieval in get_context.
# k=10 matches the FTS5 limit=10 candidate pool so the char-budget loop
# sees the same number of candidates as the legacy path — the real limiter
# is the char budget, not k itself.  The bench validated k=3 for grounding
# precision, but get_context is a candidate-retrieval step; having 10
# candidates is more conservative than restricting to 3 and letting the
# budget truncate naturally.
_SEMANTIC_K = 10

# Maximum L2 distance for a KNN hit to be considered relevant.
# vec0's default distance metric is L2; bge-small-en-v1.5 produces
# unit-normalized embeddings (norm≈1.0), so L2 and cosine are related by
# L2 = sqrt(2 * cosine_dist).
#
# Empirically calibrated against BAAI/bge-small-en-v1.5 on representative
# pairs drawn from the actual test-store vocabulary:
#   related   (lexically disjoint, semantically related): L2 ∈ [0.495, 0.882]
#   unrelated (nonsense tokens / truly disjoint domains): L2 ∈ [0.899, 1.066]
# A threshold of 0.89 admits all measured related pairs (max 0.882) and
# rejects all measured unrelated ones (min 0.899), with a ~0.017 margin on
# each side.  Calibration included the exact query used in the golden no-match
# test ("nonexistent_xyzzy" → min_l2=0.899).
# Cosine equivalence: L2=0.89 ≈ cosine_distance=0.396 (cosine_sim≈0.604).
_SEMANTIC_MAX_DISTANCE = 0.89

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
    run_id TEXT NOT NULL DEFAULT '',
    superseded_by TEXT DEFAULT NULL
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
    superseded_by: str | None = None

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
        superseded_by=row["superseded_by"],
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
        self._migrate_schema()
        # Embedding provider — use injected instance or create one via factory.
        # Default (embedder=None) is available iff the [semantic] extra / fastembed
        # is importable; otherwise available() is False and the store is FTS5-only.
        self._embedder: Embedder = embedder if embedder is not None else get_embedder(root)
        self._vec_ready: bool = False
        # _init_vec uses configured_dim (cheap — no model load), so opening a
        # MemoryStore never downloads the real fastembed model (VEC-03).
        self._init_vec()
        # Backfill is deferred to the first write so that read-only paths
        # (status, count, last_entry_at) do not trigger any embed work.
        self._backfill_pending: bool = self._vec_ready

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate_schema(self) -> None:
        """Migrate memories table to the current schema version. Never raises.

        Runs after executescript(SCHEMA_SQL) so the schema_version table already
        exists. Adds superseded_by column via PRAGMA-guarded ALTER if absent, then
        unconditionally bumps schema_version to 2 (idempotent for both fresh and
        migrated DBs). Leaves memories_fts and its triggers untouched — they
        reference only summary/content/tags.
        """
        try:
            cols = {row[1] for row in self._conn.execute("PRAGMA table_info(memories)")}
            if "superseded_by" not in cols:
                self._conn.execute(
                    "ALTER TABLE memories ADD COLUMN superseded_by TEXT DEFAULT NULL"
                )
            # Unconditional: ensures BOTH fresh and migrated DBs record version=2.
            self._conn.execute("INSERT OR REPLACE INTO schema_version(version) VALUES (2)")
            self._conn.commit()
        except Exception:
            pass

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
        include_superseded: bool = False,
    ) -> list[SearchResult]:
        if not query.strip():
            return []

        safe_query = self._sanitize_fts_query(query)
        # When include_superseded is False (default), exclude superseded rows.
        # The clause is appended to each FTS branch's WHERE so both paths filter
        # identically — byte-identical output when no rows are superseded.
        active_filter = "" if include_superseded else " AND m.superseded_by IS NULL"

        if kind is not None:
            rows = self._conn.execute(
                f"""SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?
                     AND m.kind = ?{active_filter}
                   ORDER BY rank
                   LIMIT ?""",
                (safe_query, kind.value, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"""SELECT m.*, rank
                   FROM memories_fts fts
                   JOIN memories m ON m.rowid = fts.rowid
                   WHERE memories_fts MATCH ?{active_filter}
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
        """Return memories of the given kind ordered by created_at DESC.

        Superseded rows are intentionally included; callers needing active-only
        results must check entry.superseded_by.
        """
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

        Superseded rows are intentionally included; callers needing active-only
        results must check entry.superseded_by.
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

    def supersede(self, old_id: str, new_id: str) -> bool:
        """Mark old_id as superseded by new_id. Returns True if old_id existed; False otherwise.

        Sets superseded_by=new_id on the old entry and commits. new_id is NOT validated —
        callers may supply a forward reference or any string. The memories_au AFTER UPDATE
        trigger re-syncs FTS with unchanged summary/content/tags (harmless); the vec row
        is untouched (embedding remains valid — content did not change). Never raises.
        """
        try:
            cur = self._conn.execute(
                "UPDATE memories SET superseded_by=? WHERE id=?", (new_id, old_id)
            )
            self._conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False

    def find_contradiction_candidates(
        self,
        entry: MemoryEntry,
        *,
        threshold: float = 0.9,
        same_kind: bool = True,
    ) -> list[SearchResult]:
        """Surface active memories semantically similar to entry. FLAG-ONLY — mutates nothing.

        Uses vec0 KNN to find the nearest active (non-superseded) memories, converts
        L2 distance to cosine similarity (cos = 1 - (dist**2)/2), and returns those
        with cos >= threshold. Excludes entry.id itself. Returns [] when the embedder
        is unavailable or any error occurs — never raises.

        Does NOT auto-supersede or auto-delete anything (honors ECC silent-content-loss
        caution). Callers decide what to do with the returned candidates.
        """
        try:
            if not self._vec_ready or not self._embedder.available():
                return []
            text = entry.summary + "\n" + entry.content
            vecs = self._embedder.embed([text])
            if not vecs:
                return []
            import sqlite_vec  # local import — must be loaded on this conn already

            serialized = sqlite_vec.serialize_float32(vecs[0])
            knn_rows = self._conn.execute(
                "SELECT rowid, distance FROM memories_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (serialized, _SEMANTIC_K),
            ).fetchall()
            results = []
            for knn_row in knn_rows:
                mem_row = self._conn.execute(
                    "SELECT * FROM memories WHERE rowid=? AND superseded_by IS NULL",
                    (knn_row[0],),
                ).fetchone()
                if mem_row is None:
                    continue
                if mem_row["id"] == entry.id:
                    continue
                if same_kind and mem_row["kind"] != entry.kind.value:
                    continue
                dist = knn_row[1]
                cos = 1.0 - (dist * dist) / 2.0
                if cos >= threshold:
                    results.append(SearchResult(entry=_row_to_entry(mem_row), score=cos))
            return results
        except Exception:
            return []

    def _semantic_results(self, query: str, k: int) -> list[SearchResult] | None:
        """Return KNN-ranked SearchResults for query against memories_vec, or None to fall back.

        Returns None when:
        - _vec_ready is False or embedder is unavailable
        - embedder returns an empty list for the query
        - memories_vec has zero rows (no vectors to rank)
        - all KNN neighbors exceed _SEMANTIC_MAX_DISTANCE (no relevant match)
        - any exception (degradation contract: never raises)

        The no-match path is handled on the semantic axis via the distance
        threshold — NOT via an FTS5 gate, which would suppress the lexically-
        disjoint-but-semantically-relevant case the milestone exists to serve.

        Security: serialized blob and k are bound parameters — query text is
        never interpolated into SQL (T-10-01).
        """
        try:
            if not self._vec_ready or not self._embedder.available():
                return None
            vecs = self._embedder.embed([query])
            if not vecs:
                return None
            import sqlite_vec  # local import — must be loaded on this conn already

            serialized = sqlite_vec.serialize_float32(vecs[0])
            knn_rows = self._conn.execute(
                "SELECT rowid, distance FROM memories_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (serialized, k),
            ).fetchall()
            # Filter by L2 distance threshold — keeps only semantically relevant
            # neighbors.  Without this, KNN always returns k results even for
            # unrelated queries.  _SEMANTIC_MAX_DISTANCE was empirically calibrated
            # against bge-small-en-v1.5 (see constant definition above).
            knn_rows = [r for r in knn_rows if r[1] <= _SEMANTIC_MAX_DISTANCE]
            if not knn_rows:
                return None
            results = []
            for knn_row in knn_rows:
                # Superseded rows drop out here so get_context injects current truth;
                # k may shrink below LIMIT, acceptable.
                mem_row = self._conn.execute(
                    "SELECT * FROM memories WHERE rowid=? AND superseded_by IS NULL", (knn_row[0],)
                ).fetchone()
                if mem_row is not None:
                    results.append(SearchResult(entry=_row_to_entry(mem_row), score=knn_row[1]))
            return results if results else None
        except Exception:
            return None

    def get_context(self, query: str, *, max_tokens: int = 2000, k: int = _SEMANTIC_K) -> str:
        """Return markdown-formatted context for prompt injection.

        Uses semantic KNN retrieval (memories_vec) when _vec_ready and embedder
        are both available; falls back to FTS5/BM25 search() otherwise.
        Approximate token budget via character count (1 token ~ 4 chars).
        """
        results = self._semantic_results(query, k)
        if results is None:
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
