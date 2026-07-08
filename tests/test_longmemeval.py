"""Tests for bench/longmemeval.py — offline metric-math + backend + main() tests.

All tests are offline: metric-math tests use stub ranked-id lists (no LLM/embedder);
semantic-backend tests inject a fake embed_fn; bm25 tests use real in-memory FTS5.
"""

from __future__ import annotations

import json
from pathlib import Path

import bench.longmemeval as lme
import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

_FIXTURE = Path(__file__).parent.parent / "bench" / "fixtures" / "lme_smoke.json"

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
# Loader tests
# ──────────────────────────────────────────────────────────────────────────────


def test_load_data_happy_path():
    """Loader returns a non-empty list for the smoke fixture."""
    result = lme._load_data(_FIXTURE)
    assert isinstance(result, list)
    assert len(result) > 0


def test_load_data_missing_file(tmp_path: Path):
    """Missing file -> None; never raises."""
    result = lme._load_data(tmp_path / "nope.json")
    assert result is None


def test_load_data_empty_json(tmp_path: Path):
    """Empty list JSON -> None."""
    p = tmp_path / "empty.json"
    p.write_text("[]")
    assert lme._load_data(p) is None


def test_load_data_bad_json(tmp_path: Path):
    """Bad JSON -> None; never raises."""
    p = tmp_path / "bad.json"
    p.write_text("not valid json {{{")
    assert lme._load_data(p) is None


# ──────────────────────────────────────────────────────────────────────────────
# Metric math tests — stub ranking, no embedder / FTS needed
# ──────────────────────────────────────────────────────────────────────────────


def test_recall_any_and_all_gold_in_top_k():
    """Gold in top-k -> recall_all=1.0 and recall_any=1.0."""
    ranked = ["sess-001", "sess-002", "sess-003"]
    gold = ["sess-001"]
    assert lme._recall_any(ranked, gold, k=5) == 1.0
    assert lme._recall_all(ranked, gold, k=5) == 1.0


def test_recall_any_and_all_gold_not_in_top_k():
    """Gold NOT in ranked top-k -> both 0.0."""
    ranked = ["sess-999", "sess-998"]
    gold = ["sess-001"]
    assert lme._recall_any(ranked, gold, k=5) == 0.0
    assert lme._recall_all(ranked, gold, k=5) == 0.0


def test_recall_diverges_multi_gold():
    """Multi-gold with only one of two golds in top-k -> recall_any=1.0, recall_all=0.0."""
    # sess-005 is in ranked, sess-006 is NOT -> recall_any=1.0 (found one), recall_all=0.0 (missed one)
    ranked = ["sess-005", "sess-007", "sess-008"]
    gold = ["sess-005", "sess-006"]
    assert lme._recall_any(ranked, gold, k=5) == 1.0
    assert lme._recall_all(ranked, gold, k=5) == 0.0


def test_recall_all_only_when_all_present():
    """recall_all=1.0 only when BOTH golds appear in top-k."""
    ranked = ["sess-005", "sess-006", "sess-007"]
    gold = ["sess-005", "sess-006"]
    assert lme._recall_all(ranked, gold, k=5) == 1.0
    assert lme._recall_any(ranked, gold, k=5) == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# BM25 backend test — real in-memory FTS5
# ──────────────────────────────────────────────────────────────────────────────


def test_bm25_backend_on_lme_smoke():
    """BM25 returns the gold session id for the on-topic instance within top-10."""
    data = lme._load_data(_FIXTURE)
    assert data is not None

    # Find the single-gold instance (lme-001 about replication factor)
    instance = next(
        (d for d in data if d.get("answer_session_ids") and len(d["answer_session_ids"]) == 1),
        None,
    )
    assert instance is not None, "smoke fixture must have a single-gold instance"

    from bench._retrieval import bm25_rank

    docs = lme._build_docs(instance)
    assert docs is not None, "_build_docs must succeed on a valid instance"

    gold_id = instance["answer_session_ids"][0]
    ranked = bm25_rank(docs, instance["question"], k=10)
    assert gold_id in ranked, f"expected {gold_id} in top-10, got {ranked}"


# ──────────────────────────────────────────────────────────────────────────────
# Semantic backend test — injected fake embed_fn
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_semantic_backend_with_fake_embedder():
    """Semantic backend with injected fake embed_fn returns gold session in top-k."""
    data = lme._load_data(_FIXTURE)
    assert data is not None

    instance = next(
        (d for d in data if d.get("answer_session_ids") and len(d["answer_session_ids"]) == 1),
        None,
    )
    assert instance is not None

    gold_id = instance["answer_session_ids"][0]
    docs = lme._build_docs(instance)
    assert docs is not None

    # The gold session (sess-001) discusses "replication factor" -> keyword for discriminating embed
    # The question also contains "replication" -> query gets match_vec -> gold ranks closest
    embed_fn = _fake_embed_factory("replication", [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])

    from bench._retrieval import semantic_rank

    ranked = semantic_rank(docs, instance["question"], k=10, embed_fn=embed_fn)
    assert gold_id in ranked, f"expected {gold_id} in top-10, got {ranked}"


# ──────────────────────────────────────────────────────────────────────────────
# Semantic unavailable — arm skipped, bm25 still runs
# ──────────────────────────────────────────────────────────────────────────────


def test_semantic_unavailable_bm25_still_runs(tmp_path: Path, capsys, monkeypatch):
    """Semantic arm skipped (printed note) when unavailable; bm25 still runs; main() -> 0."""
    import bench._retrieval as retrieval

    monkeypatch.setattr(retrieval, "semantic_backend_available", lambda model: (None, False))

    out_file = tmp_path / "out.json"
    rc = lme.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25,semantic",
            "--k",
            "5,10",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "semantic" in out.lower() or "skip" in out.lower(), (
        f"expected note about semantic skip, got: {out!r}"
    )
    data = json.loads(out_file.read_text())
    assert "bm25" in data["backends"], "bm25 backend must appear in output when semantic is skipped"
    assert "semantic" not in data["backends"], "semantic backend must be absent when unavailable"


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end main() tests
# ──────────────────────────────────────────────────────────────────────────────


def test_main_bm25_end_to_end(tmp_path: Path):
    """main() with bm25 backend returns 0; JSON has expected structure."""
    out_file = tmp_path / "lme.json"
    rc = lme.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--k",
            "5,10",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0, f"expected rc=0, got {rc}"

    data = json.loads(out_file.read_text())
    assert data["benchmark"] == "longmemeval"
    assert "n_instances" in data
    assert "skipped" in data
    assert "embed_model" in data
    assert "backends" in data

    bm25 = data["backends"]["bm25"]
    assert "recall_all" in bm25
    assert "recall_any" in bm25

    # Check k=5 stats structure
    ra5 = bm25["recall_all"].get("5") or bm25["recall_all"].get(5)
    assert ra5 is not None, f"expected key '5' in recall_all, got {list(bm25['recall_all'].keys())}"
    assert "mean" in ra5
    assert "n" in ra5
    assert "wilson_ci" in ra5

    # Check k=10 stats structure
    ra10 = bm25["recall_all"].get("10") or bm25["recall_all"].get(10)
    assert ra10 is not None, "expected key '10' in recall_all"


def test_main_missing_data_returns_nonzero(tmp_path: Path):
    """Missing data file -> note printed, returns non-zero."""
    out_file = tmp_path / "out.json"
    rc = lme.main(
        ["--data", str(tmp_path / "nope.json"), "--backends", "bm25", "--out", str(out_file)]
    )
    assert rc != 0


def test_main_malformed_instance_skipped(tmp_path: Path):
    """Malformed instance (missing haystack fields) is skipped; no exception; rc is int."""
    data_file = tmp_path / "data.json"
    data_file.write_text(
        json.dumps(
            [
                {
                    "question_id": "bad-001",
                    "question_type": "single_session",
                    "question": "Q about acks?",
                    "answer": "A",
                    "question_date": "2024-01-01",
                    # Missing haystack_session_ids / haystack_sessions
                    "answer_session_ids": ["sess-X"],
                }
            ]
        )
    )
    out_file = tmp_path / "out.json"
    rc = lme.main(
        ["--data", str(data_file), "--backends", "bm25", "--k", "5", "--out", str(out_file)]
    )
    # Must not raise; rc 0 or non-zero both acceptable (skipped instance)
    assert isinstance(rc, int)


def test_main_abstention_instance_counted_in_skipped(tmp_path: Path):
    """Instance with empty answer_session_ids is counted in 'skipped'."""
    out_file = tmp_path / "out.json"
    rc = lme.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--k",
            "5",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    data = json.loads(out_file.read_text())
    # Smoke fixture has one abstention instance (lme-003 with empty answer_session_ids)
    assert data.get("skipped", 0) > 0, "abstention instance must be counted in skipped"
