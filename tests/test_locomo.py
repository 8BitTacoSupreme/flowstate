"""Tests for bench/locomo.py — offline metric-math + backend + main() tests.

All tests are offline: metric-math tests use pure coverage functions (no retrieval);
semantic-backend tests inject a fake embed_fn; bm25 tests use real in-memory FTS5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bench.locomo as loc

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

_FIXTURE = Path(__file__).parent.parent / "bench" / "fixtures" / "locomo_smoke.json"

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
    result = loc._load_data(_FIXTURE)
    assert isinstance(result, list)
    assert len(result) > 0


def test_load_data_missing_file(tmp_path: Path):
    """Missing file -> None; never raises."""
    result = loc._load_data(tmp_path / "nope.json")
    assert result is None


def test_load_data_empty_json(tmp_path: Path):
    """Empty list -> None."""
    p = tmp_path / "empty.json"
    p.write_text("[]")
    assert loc._load_data(p) is None


def test_load_data_bad_json(tmp_path: Path):
    """Bad JSON -> None; never raises."""
    p = tmp_path / "bad.json"
    p.write_text("not valid json")
    assert loc._load_data(p) is None


# ──────────────────────────────────────────────────────────────────────────────
# Metric math tests — pure coverage functions, no retrieval backend
# ──────────────────────────────────────────────────────────────────────────────


def test_coverage_partial_one_of_two_retrieved():
    """qa with 2 evidence ids, 1 in retrieved -> coverage==0.5, full_coverage==0."""
    gold = ["D001", "D002"]
    retrieved = ["D001", "D003", "D004"]
    assert abs(loc._coverage(gold, retrieved) - 0.5) < 1e-9
    assert loc._full_coverage(gold, retrieved) == 0


def test_coverage_all_evidence_retrieved():
    """All evidence ids in retrieved -> coverage==1.0, full_coverage==1."""
    gold = ["D001", "D002"]
    retrieved = ["D001", "D002", "D003"]
    assert abs(loc._coverage(gold, retrieved) - 1.0) < 1e-9
    assert loc._full_coverage(gold, retrieved) == 1


def test_coverage_none_retrieved():
    """No gold ids in retrieved -> coverage==0.0, full_coverage==0."""
    gold = ["D001", "D002"]
    retrieved = ["D003", "D004", "D005"]
    assert loc._coverage(gold, retrieved) == 0.0
    assert loc._full_coverage(gold, retrieved) == 0


def test_coverage_single_evidence_retrieved():
    """Single evidence id retrieved -> coverage==1.0, full_coverage==1."""
    gold = ["D002"]
    retrieved = ["D002", "D001"]
    assert abs(loc._coverage(gold, retrieved) - 1.0) < 1e-9
    assert loc._full_coverage(gold, retrieved) == 1


def test_coverage_empty_gold():
    """Empty gold_evidence -> coverage==0.0 (caller should have skipped this qa)."""
    assert loc._coverage([], ["D001", "D002"]) == 0.0
    assert loc._full_coverage([], ["D001"]) == 0


# ──────────────────────────────────────────────────────────────────────────────
# BM25 backend test — real in-memory FTS5
# ──────────────────────────────────────────────────────────────────────────────


def test_bm25_backend_on_locomo_smoke_single_evidence():
    """BM25 returns the gold dia_id for the on-topic single-evidence qa within top-5."""
    data = loc._load_data(_FIXTURE)
    assert data is not None
    conv = data[0]

    docs = loc._build_docs(conv)
    assert len(docs) > 0, "build_docs must return turns from the conversation"

    # Find single-evidence qa (evidence: ["D002"] about exactly-once producer semantics)
    qa = next(
        (q for q in conv["qa"] if len(q.get("evidence", [])) == 1),
        None,
    )
    assert qa is not None, "smoke fixture must have a single-evidence qa"

    from bench._retrieval import bm25_rank

    gold_ids = qa["evidence"]
    ranked = bm25_rank(docs, qa["question"], k=5)
    assert any(g in ranked for g in gold_ids), (
        f"expected gold {gold_ids} in top-5 bm25 results, got {ranked}"
    )


def test_bm25_backend_on_locomo_smoke_multi_evidence():
    """BM25 returns at least one gold dia_id for the 2-evidence qa within top-5."""
    data = loc._load_data(_FIXTURE)
    assert data is not None
    conv = data[0]

    docs = loc._build_docs(conv)

    # Find 2-evidence qa
    qa = next(
        (q for q in conv["qa"] if len(q.get("evidence", [])) == 2),
        None,
    )
    assert qa is not None, "smoke fixture must have a 2-evidence qa"

    from bench._retrieval import bm25_rank

    ranked = bm25_rank(docs, qa["question"], k=5)
    gold_ids = qa["evidence"]
    assert any(g in ranked for g in gold_ids), (
        f"expected at least one of {gold_ids} in top-5, got {ranked}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Semantic backend test — injected fake embed_fn
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_semantic_backend_with_fake_embedder():
    """Semantic backend with injected fake embed_fn returns gold dia_id in top-5."""
    data = loc._load_data(_FIXTURE)
    assert data is not None
    conv = data[0]

    docs = loc._build_docs(conv)

    # Find qa with evidence D002 (D002 text contains "exactly-once")
    qa = next(
        (q for q in conv["qa"] if q.get("evidence") == ["D002"]),
        None,
    )
    assert qa is not None, "smoke fixture must have qa with evidence ['D002']"

    # "exactly-once" appears in D002 and in the question -> D002 gets match_vec (distance 0 from query)
    embed_fn = _fake_embed_factory("exactly-once", [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])

    from bench._retrieval import semantic_rank

    ranked = semantic_rank(docs, qa["question"], k=5, embed_fn=embed_fn)
    assert "D002" in ranked, f"expected D002 in top-5, got {ranked}"


# ──────────────────────────────────────────────────────────────────────────────
# Semantic unavailable — arm skipped, bm25 still runs
# ──────────────────────────────────────────────────────────────────────────────


def test_semantic_unavailable_bm25_still_runs(tmp_path: Path, capsys, monkeypatch):
    """Semantic arm skipped (note printed) when unavailable; bm25 still runs; main() -> 0."""
    import bench._retrieval as retrieval

    monkeypatch.setattr(retrieval, "semantic_backend_available", lambda model: (None, False))

    out_file = tmp_path / "out.json"
    rc = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25,semantic",
            "--top-n",
            "5",
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
    assert "bm25" in data["backends"], "bm25 must be present when semantic is skipped"
    assert "semantic" not in data["backends"], "semantic must be absent when unavailable"


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end main() tests
# ──────────────────────────────────────────────────────────────────────────────


def test_main_bm25_end_to_end(tmp_path: Path):
    """main() with bm25 backend returns 0; JSON has expected structure."""
    out_file = tmp_path / "loc.json"
    rc = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0, f"expected rc=0, got {rc}"

    data = json.loads(out_file.read_text())
    assert data["benchmark"] == "locomo"
    assert "n_qa" in data
    assert "skipped" in data
    assert "top_n" in data
    assert "embed_model" in data
    assert "backends" in data

    bm25 = data["backends"]["bm25"]
    assert "mean_coverage" in bm25
    assert "full_coverage_rate" in bm25
    assert "wilson_ci" in bm25
    assert "n" in bm25


def test_main_missing_data_returns_nonzero(tmp_path: Path):
    """Missing data file -> note printed, returns non-zero."""
    out_file = tmp_path / "out.json"
    rc = loc.main(
        ["--data", str(tmp_path / "nope.json"), "--backends", "bm25", "--out", str(out_file)]
    )
    assert rc != 0


def test_main_empty_evidence_qa_skipped(tmp_path: Path):
    """QA item with empty evidence is skipped and counted in 'skipped'."""
    out_file = tmp_path / "out.json"
    rc = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    data = json.loads(out_file.read_text())
    # Smoke fixture has one abstention qa (empty evidence)
    assert data.get("skipped", 0) > 0, "empty-evidence qa must be counted in skipped"


# ──────────────────────────────────────────────────────────────────────────────
# _build_observation_docs — offline unit tests
# ──────────────────────────────────────────────────────────────────────────────


def test_build_observation_docs_string_dia():
    """String dia_id row -> one (dia_id, text) doc."""
    conv = {
        "observation": {
            "session_1_observation": {
                "Alice": [["Alice loves hiking.", "D1:1"]],
            }
        }
    }
    docs = loc._build_observation_docs(conv)
    assert docs == [("D1:1", "Alice loves hiking.")]


def test_build_observation_docs_list_of_dia_ids():
    """List-of-dia_ids row -> one doc per id, same text."""
    conv = {
        "observation": {
            "session_1_observation": {
                "Bob": [["Bob works remotely.", ["D2:1", "D2:2"]]],
            }
        }
    }
    docs = loc._build_observation_docs(conv)
    assert sorted(docs) == sorted(
        [
            ("D2:1", "Bob works remotely."),
            ("D2:2", "Bob works remotely."),
        ]
    )


def test_build_observation_docs_multiple_speakers_and_sessions():
    """Multiple speakers/sessions all contribute docs."""
    conv = {
        "observation": {
            "session_1_observation": {
                "Alice": [["Alice loves hiking.", "D1:1"]],
                "Bob": [["Bob works remotely.", "D1:2"]],
            },
            "session_2_observation": {
                "Alice": [["Alice adopted a dog.", "D2:1"]],
            },
        }
    }
    docs = loc._build_observation_docs(conv)
    assert set(docs) == {
        ("D1:1", "Alice loves hiking."),
        ("D1:2", "Bob works remotely."),
        ("D2:1", "Alice adopted a dog."),
    }


def test_build_observation_docs_malformed_rows_skipped():
    """Non-list rows, wrong-length rows, and non-dict session values are skipped."""
    conv = {
        "observation": {
            "session_1_observation": {
                "Alice": [
                    ["Alice loves hiking.", "D1:1"],  # valid
                    "not-a-list",  # malformed: not a list/tuple
                    ["only-one-element"],  # malformed: wrong length
                    ["too", "many", "elements"],  # malformed: wrong length
                ],
                "Bob": "not-a-list-of-rows",  # malformed: speaker value not a list
            },
            "session_2_observation": "not-a-dict",  # malformed: session value not a dict
        }
    }
    docs = loc._build_observation_docs(conv)
    assert docs == [("D1:1", "Alice loves hiking.")]


def test_build_observation_docs_missing_observation_key():
    """Missing 'observation' key -> [] (never raises)."""
    assert loc._build_observation_docs({}) == []
    assert loc._build_observation_docs({"conversation": {}}) == []


def test_build_observation_docs_never_raises_on_garbage():
    """Wildly malformed input never raises; returns []."""
    assert loc._build_observation_docs({"observation": None}) == []
    assert loc._build_observation_docs({"observation": []}) == []
    assert loc._build_observation_docs({"observation": {"session_1_observation": None}}) == []


# ──────────────────────────────────────────────────────────────────────────────
# --corpus flag — end-to-end main() tests with inline tmp_path fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _write_observations_conv(tmp_path: Path) -> Path:
    """Write a tiny inline conv with conversation + observation + qa to a tmp JSON file."""
    conv = {
        "qa": [
            {
                "question": "What hobby does Alice enjoy?",
                "evidence": ["D1:1"],
            }
        ],
        "conversation": {
            "session_1": [
                {"speaker": "Alice", "dia_id": "D1:1", "text": "Alice loves hiking on weekends."},
                {"speaker": "Bob", "dia_id": "D1:2", "text": "Bob prefers reading books."},
            ],
        },
        "observation": {
            "session_1_observation": {
                "Alice": [["Alice loves hiking on weekends.", "D1:1"]],
                "Bob": [["Bob prefers reading books.", "D1:2"]],
            },
        },
    }
    p = tmp_path / "observations_conv.json"
    p.write_text(json.dumps([conv]))
    return p


def test_corpus_observations_end_to_end_retrieves_gold_evidence(tmp_path: Path):
    """--corpus observations retrieves the gold dia_id from observation docs within top-n."""
    data_file = _write_observations_conv(tmp_path)
    out_file = tmp_path / "out.json"
    rc = loc.main(
        [
            "--data",
            str(data_file),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--corpus",
            "observations",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    data = json.loads(out_file.read_text())
    assert data["corpus"] == "observations"
    bm25 = data["backends"]["bm25"]
    assert bm25["n"] == 1
    assert bm25["mean_coverage"] == 1.0
    assert bm25["full_coverage_rate"] == 1.0


def test_corpus_default_is_turns(tmp_path: Path):
    """Omitting --corpus defaults to 'turns' and is recorded in the output JSON."""
    out_file = tmp_path / "out.json"
    rc = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--out",
            str(out_file),
        ]
    )
    assert rc == 0
    data = json.loads(out_file.read_text())
    assert data["corpus"] == "turns"


def test_corpus_turns_explicit_matches_default(tmp_path: Path):
    """--corpus turns explicitly produces byte-identical results to the default (omitted) case."""
    out_default = tmp_path / "default.json"
    out_explicit = tmp_path / "explicit.json"
    rc1 = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--out",
            str(out_default),
        ]
    )
    rc2 = loc.main(
        [
            "--data",
            str(_FIXTURE),
            "--backends",
            "bm25",
            "--top-n",
            "5",
            "--corpus",
            "turns",
            "--out",
            str(out_explicit),
        ]
    )
    assert rc1 == 0
    assert rc2 == 0
    assert out_default.read_text() == out_explicit.read_text()
