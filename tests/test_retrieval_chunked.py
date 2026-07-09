"""Tests for chunk-level semantic retrieval (bench/_retrieval.py).

LongMemEval sessions routinely exceed bge's 512-token embedding cap (median
~2500 tokens), so plain semantic_rank only "sees" the truncated head of each
document. These tests prove `semantic_rank_chunked` recovers matches that live
deeper in a document by embedding fixed-size windows and rolling scores up to
the parent doc via max-sim (best chunk wins).
"""

from __future__ import annotations

import sys

import pytest

import bench._retrieval as r

try:
    import sqlite_vec  # noqa: F401

    _HAS_VEC = True
except Exception:
    _HAS_VEC = False


def _fake_embed_factory(keyword: str, match_vec: list[float], default_vec: list[float]):
    """Return a fake embed_fn: texts containing keyword -> match_vec, others -> default_vec."""

    def embed_fn(texts: list[str]) -> list[list[float]]:
        return [match_vec[:] if keyword in t else default_vec[:] for t in texts]

    return embed_fn


# ──────────────────────────────────────────────────────────────────────────────
# _chunk_text: whitespace-boundary packing
# ──────────────────────────────────────────────────────────────────────────────


def test_chunking_splits_long_doc():
    """A long doc splits into >1 chunk; a short doc stays a single chunk; no word is cut."""
    long_text = " ".join(f"word{i}" for i in range(200))
    chunks = r._chunk_text(long_text, chunk_tokens=10)
    assert len(chunks) > 1
    # Rejoining the chunks must reproduce the exact original word sequence —
    # proves packing never cuts a word mid-token or drops/duplicates words.
    assert " ".join(chunks).split() == long_text.split()

    short_text = "just a few words here"
    chunks_short = r._chunk_text(short_text, chunk_tokens=400)
    assert len(chunks_short) == 1
    assert chunks_short[0] == short_text


def test_chunking_blank_text_yields_no_chunks():
    """Blank/empty text contributes nothing."""
    assert r._chunk_text("", chunk_tokens=10) == []
    assert r._chunk_text("   ", chunk_tokens=10) == []


# ──────────────────────────────────────────────────────────────────────────────
# semantic_rank_chunked: max-sim rollup — THE core test
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_max_sim_rollup():
    """A doc whose match lives in its SECOND chunk ranks first under chunked
    retrieval, even though plain semantic_rank (which only sees a truncated
    head-window of the whole doc) misses it entirely.
    """
    chunk_tokens = 5  # chunk_chars = 20, matches the head_chars truncation below
    head_chars = chunk_tokens * 4

    match_vec = [1.0, 0.0]
    distractor_vec = [0.5, 0.5]
    default_vec = [0.0, 1.0]

    def embed_fn(texts: list[str]) -> list[list[float]]:
        # Simulates a real embedder's fixed-token-window truncation: only the
        # first head_chars of any given text are ever "seen" by the embedder.
        out = []
        for t in texts:
            probe = t[:head_chars]
            if "GOLDMATCH" in probe:
                out.append(match_vec[:])
            elif "distractorfiller" in probe:
                out.append(distractor_vec[:])
            else:
                out.append(default_vec[:])
        return out

    # GOLDMATCH lands in the doc's SECOND chunk (first chunk is filler that
    # exactly fills the chunk window).
    gold_text = "aaaa bbbb cccc dddd GOLDMATCH tail"
    # distractorfiller never overlaps GOLDMATCH; its head is closer to the
    # query than gold's (truncated) head, so plain semantic_rank should
    # actually prefer the distractor over gold.
    distractor_text = "distractorfiller aaaa bbbb cccc dddd eeee"

    docs = [("gold", gold_text), ("distractor", distractor_text)]

    chunked_ranked = r.semantic_rank_chunked(
        docs, "GOLDMATCH", k=1, embed_fn=embed_fn, chunk_tokens=chunk_tokens
    )
    assert chunked_ranked == ["gold"], (
        f"expected chunked to recover gold first, got {chunked_ranked}"
    )

    plain_ranked = r.semantic_rank(docs, "GOLDMATCH", k=1, embed_fn=embed_fn)
    assert plain_ranked != ["gold"], (
        f"plain semantic_rank should NOT rank gold first (it only sees the "
        f"truncated head), got {plain_ranked}"
    )


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_dedup():
    """A doc whose multiple chunks all match the query appears exactly once."""
    # Long doc, every word is GOLDMATCH -> every chunk matches -> without
    # dedup this doc_id would appear once per matching chunk.
    text = " ".join(["GOLDMATCH"] * 60)
    docs = [("gold", text)]
    embed_fn = _fake_embed_factory("GOLDMATCH", [1.0, 0.0], [0.0, 1.0])

    ranked = r.semantic_rank_chunked(docs, "GOLDMATCH", k=5, embed_fn=embed_fn, chunk_tokens=5)
    assert ranked == ["gold"], f"expected exactly one gold entry, got {ranked}"


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_k_semantics():
    """With 3+ matching docs and k=2, result length is exactly 2."""
    docs = [
        ("doc-a", "GOLDMATCH one"),
        ("doc-b", "GOLDMATCH two"),
        ("doc-c", "GOLDMATCH three"),
    ]
    embed_fn = _fake_embed_factory("GOLDMATCH", [1.0, 0.0], [0.0, 1.0])

    ranked = r.semantic_rank_chunked(docs, "GOLDMATCH", k=2, embed_fn=embed_fn, chunk_tokens=400)
    assert len(ranked) == 2


# ──────────────────────────────────────────────────────────────────────────────
# never-raises
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_never_raises_embed_error():
    """embed_fn that raises -> semantic_rank_chunked returns [] (never propagates)."""

    def raising_embed_fn(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embed backend exploded")

    docs = [("doc-a", "some session text here")]
    ranked = r.semantic_rank_chunked(
        docs, "query", k=5, embed_fn=raising_embed_fn, chunk_tokens=400
    )
    assert ranked == []


def test_never_raises_no_vec(monkeypatch):
    """Missing sqlite_vec (simulated) -> [] ; never propagates."""
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)

    def embed_fn(texts: list[str]) -> list[list[float]]:
        return [[0.0, 1.0] for _ in texts]

    docs = [("doc-a", "some session text here")]
    ranked = r.semantic_rank_chunked(docs, "query", k=5, embed_fn=embed_fn, chunk_tokens=400)
    assert ranked == []


def test_blank_query_or_empty_docs_returns_empty():
    """Blank query or empty docs -> [] without touching sqlite_vec/embed_fn."""

    def embed_fn(texts: list[str]) -> list[list[float]]:
        raise AssertionError("embed_fn must not be called for blank query / empty docs")

    assert r.semantic_rank_chunked([], "query", k=5, embed_fn=embed_fn) == []
    assert r.semantic_rank_chunked([("a", "text")], "   ", k=5, embed_fn=embed_fn) == []
