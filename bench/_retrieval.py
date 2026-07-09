"""Shared in-memory retrieval backends for LongMemEval and LoCoMo harnesses.

Provides bm25_rank (FTS5/BM25) and semantic_rank (sqlite-vec KNN) over
(id, text) document lists.  Both functions are never-raises: any exception
is caught, printed, and [] is returned.

fastembed and sqlite_vec are OPTIONAL runtime dependencies.
semantic_backend_available() degrades gracefully when either is absent.
"""

from __future__ import annotations

import sqlite3

from bench.grounding import (  # noqa: F401  (re-export for AND-style callers)
    _default_embedder,
    _sanitize_fts_query,
)


def _fts5_or_query(query: str) -> str:
    """Build a disjunctive (OR) FTS5 MATCH expression from a raw query string.

    Each whitespace-separated token is quoted to prevent FTS5 operator
    interpretation, then joined with OR.  Disjunctive matching is appropriate
    for short documents (conversation turns) where a conjunctive AND query
    would require every token to appear in each turn.  FTS5's BM25 ranking
    still scores results by term frequency, so the most-relevant document
    surfaces first even with OR semantics.

    _sanitize_fts_query (from bench.grounding) is re-exported here for callers
    that need AND semantics over long documents (e.g., wiki articles).
    """
    tokens = query.split()
    if not tokens:
        return query
    return " OR ".join(f'"{t.replace(chr(34), "")}"' for t in tokens)


def bm25_rank(docs: list[tuple[str, str]], query: str, k: int) -> list[str]:
    """BM25/FTS5 ranking over (id, text) in-memory docs.

    Builds a transient FTS5 table, inserts docs, runs a disjunctive (OR)
    MATCH query ranked by BM25, returns up to k doc-ids most-relevant-first.
    Disjunctive matching is used so that short documents (individual
    conversation turns) can be ranked without requiring every query token to
    appear verbatim.  Blank query or empty docs -> [].
    Any exception is caught and [] is returned with a printed note.

    Args:
        docs: List of (id, text) pairs.
        query: Free-text query string.
        k: Maximum number of results to return.

    Returns:
        List of doc ids, most-relevant first, length <= k.
    """
    try:
        if not docs or not query.strip():
            return []
        safe = _fts5_or_query(query)
        if not safe.strip():
            return []
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE docs USING fts5("
                "id UNINDEXED, content, tokenize='porter unicode61')"
            )
            for doc_id, text in docs:
                conn.execute("INSERT INTO docs (id, content) VALUES (?, ?)", (doc_id, text))
            rows = conn.execute(
                "SELECT id FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?",
                (safe, k),
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]
    except Exception as exc:
        print(f"note: bm25_rank failed: {exc}")
        return []


def semantic_rank(
    docs: list[tuple[str, str]],
    query: str,
    k: int,
    embed_fn,
) -> list[str]:
    """Semantic KNN ranking via sqlite-vec over (id, text) in-memory docs.

    Embeds all doc texts and the query via embed_fn, inserts into a vec0
    virtual table, and returns up to k doc-ids ordered by ascending L2
    distance (nearest first).  Blank query or empty docs -> [].
    Any exception (including missing sqlite_vec or embed_fn failure) is caught,
    printed, and [] is returned — never raises.

    Args:
        docs: List of (id, text) pairs.
        query: Free-text query string.
        k: Maximum number of results to return.
        embed_fn: Callable(list[str]) -> list[list[float]] for embedding.

    Returns:
        List of doc ids, nearest first, length <= k.
    """
    try:
        if not docs or not query.strip():
            return []

        import sqlite_vec  # local import — runtime dep confirmed by caller

        ids = [doc_id for doc_id, _ in docs]
        texts = [text for _, text in docs]

        vectors = embed_fn(texts)
        qvec = embed_fn([query])[0]
        dim = len(qvec)

        conn = sqlite3.connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute(f"CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])")
            for i, vec in enumerate(vectors):
                conn.execute(
                    "INSERT INTO vec_docs(rowid, embedding) VALUES (?, ?)",
                    (i, sqlite_vec.serialize_float32(vec)),
                )
            rows = conn.execute(
                "SELECT rowid, distance FROM vec_docs "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(qvec), k),
            ).fetchall()
        finally:
            conn.close()

        return [ids[r[0]] for r in rows]
    except Exception as exc:
        print(f"note: semantic_rank failed: {exc}")
        return []


def _chunk_text(text: str, chunk_tokens: int) -> list[str]:
    """Split text into whitespace-boundary windows sized ~chunk_tokens*4 chars.

    Words are packed greedily into a window without ever cutting a word
    mid-token. A text shorter than one window yields a single-element list.
    Blank/empty text yields [].

    Args:
        text: Raw text to chunk.
        chunk_tokens: Approximate token budget per chunk (chars = tokens*4).

    Returns:
        List of chunk strings, in original order.
    """
    words = text.split()
    if not words:
        return []

    chunk_chars = max(chunk_tokens, 1) * 4
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for word in words:
        added_len = len(word) if not current else len(word) + 1
        if current and current_len + added_len > chunk_chars:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += added_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def semantic_rank_chunked(
    docs: list[tuple[str, str]],
    query: str,
    k: int,
    embed_fn,
    *,
    chunk_tokens: int = 400,
) -> list[str]:
    """Chunk-level semantic KNN ranking with max-sim rollup to the parent doc.

    Each doc is split into ~chunk_tokens-sized windows (see _chunk_text), all
    chunks (across all docs) are embedded and inserted into a vec0 table, and
    KNN is run over the full chunk set. A doc's score is its BEST (min-distance)
    chunk; doc ids are deduped and the top-k nearest doc ids are returned.

    This recovers matches that live beyond a real embedder's fixed-token
    truncation window — plain semantic_rank only ever sees the (possibly
    truncated) whole-doc text, so a match buried deep in a long document can
    be invisible to it even though it's well within the doc.

    Blank query or empty docs -> [].  Any exception (missing sqlite_vec,
    embed_fn failure, etc.) is caught, printed, and [] is returned — never
    raises.

    Args:
        docs: List of (id, text) pairs.
        query: Free-text query string.
        k: Maximum number of doc ids to return.
        embed_fn: Callable(list[str]) -> list[list[float]] for embedding.
        chunk_tokens: Approximate token budget per chunk (default 400).

    Returns:
        List of doc ids, nearest (best chunk) first, length <= k.
    """
    try:
        if not docs or not query.strip():
            return []

        import sqlite_vec  # local import — runtime dep confirmed by caller

        flat_chunks: list[str] = []
        chunk_doc_ids: list[str] = []
        for doc_id, text in docs:
            for chunk in _chunk_text(text, chunk_tokens):
                flat_chunks.append(chunk)
                chunk_doc_ids.append(doc_id)

        if not flat_chunks:
            return []

        vectors = embed_fn(flat_chunks)
        qvec = embed_fn([query])[0]
        dim = len(qvec)

        conn = sqlite3.connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.execute(f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{dim}])")
            for i, vec in enumerate(vectors):
                conn.execute(
                    "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                    (i, sqlite_vec.serialize_float32(vec)),
                )
            rows = conn.execute(
                "SELECT rowid, distance FROM vec_chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(qvec), len(flat_chunks)),
            ).fetchall()
        finally:
            conn.close()

        best_distance: dict[str, float] = {}
        for rowid, distance in rows:
            doc_id = chunk_doc_ids[rowid]
            if doc_id not in best_distance or distance < best_distance[doc_id]:
                best_distance[doc_id] = distance

        ranked_doc_ids = sorted(best_distance, key=lambda d: best_distance[d])
        return ranked_doc_ids[:k]
    except Exception as exc:
        print(f"note: semantic_rank_chunked failed: {exc}")
        return []


def semantic_backend_available(embed_model: str) -> tuple:
    """Probe whether the semantic backend (fastembed + sqlite_vec) is available.

    Attempts to import sqlite_vec and build an embed_fn via _default_embedder.
    Returns (embed_fn, True) on success, or (None, False) on any failure.

    Mirrors the wikivec guard in bench/grounding.py.

    Args:
        embed_model: Model name to pass to _default_embedder.

    Returns:
        Tuple of (embed_fn | None, bool).
    """
    try:
        import sqlite_vec  # noqa: F401

        embed_fn = _default_embedder(embed_model)
        return (embed_fn, True)
    except Exception:
        return (None, False)
