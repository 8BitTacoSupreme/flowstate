"""Tests for bench/grounding.py — all subprocess calls mocked; no live claude."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import bench.grounding as g

# ──────────────────────────────────────────────────────────────────────────────
# Minimal stubs for build_context_prefix and MemoryStore
# ──────────────────────────────────────────────────────────────────────────────


def _bcp(root, memory, query, **kw):
    """Stub build_context_prefix: records include_layers kwarg, returns empty prefix."""
    return ""


class _Mem:
    """Stub MemoryStore context manager that never touches disk."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# _load_probes tests
# ──────────────────────────────────────────────────────────────────────────────


def test_load_probes_missing_returns_none_no_subprocess(monkeypatch, tmp_path: Path):
    """Missing file -> None; subprocess.run must NOT be called."""
    run_mock = MagicMock()
    monkeypatch.setattr(subprocess, "run", run_mock)

    result = g._load_probes(tmp_path / "nope.json")

    assert result is None
    assert run_mock.call_count == 0


def test_load_probes_empty_and_bad_json_return_none(tmp_path: Path):
    """Empty list and garbage text both -> None."""
    empty = tmp_path / "empty.json"
    empty.write_text("[]")
    assert g._load_probes(empty) is None

    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {{{")
    assert g._load_probes(bad) is None


# ──────────────────────────────────────────────────────────────────────────────
# main — missing probes guard
# ──────────────────────────────────────────────────────────────────────────────


def test_main_missing_probes_nonzero_no_subprocess(monkeypatch, tmp_path: Path):
    """main with missing probes file returns 1 (non-zero) and never calls subprocess.run."""
    run_mock = MagicMock()
    monkeypatch.setattr(subprocess, "run", run_mock)
    monkeypatch.setattr(g, "build_context_prefix", _bcp)
    monkeypatch.setattr(g, "MemoryStore", _Mem)

    rc = g.main(["--root", str(tmp_path), "--probes", str(tmp_path / "nope.json")])

    assert rc == 1
    assert run_mock.call_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# _wilson tests
# ──────────────────────────────────────────────────────────────────────────────


def test_wilson_bounds():
    """_wilson(1,2): low<=0.5<=high with both in [0,1]; _wilson(0,0)==(0.0,0.0)."""
    lo, hi = g._wilson(1, 2)
    assert 0 <= lo <= 0.5 <= hi <= 1

    assert g._wilson(0, 0) == (0.0, 0.0)


# ──────────────────────────────────────────────────────────────────────────────
# _factcheck vote tests
# ──────────────────────────────────────────────────────────────────────────────


def test_factcheck_majority_true(monkeypatch):
    """YES/YES/NO -> majority True (2 of 3 judges agree, threshold > 1.5)."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    responses = ["YES", "YES", "NO"]
    call_idx = [0]

    class _P:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kw):
        p = _P()
        p.stdout = responses[call_idx[0]]
        call_idx[0] += 1
        return p

    monkeypatch.setattr(subprocess, "run", fake_run)

    votes = [g._factcheck("some answer", "ground truth", "m") for _ in range(3)]
    yes = sum(1 for v in votes if v is True)
    majority = yes > len(votes) / 2
    assert majority is True


def test_factcheck_majority_false(monkeypatch):
    """NO/NO/YES -> majority False (1 of 3)."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    responses = ["NO", "NO", "YES"]
    call_idx = [0]

    class _P:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kw):
        p = _P()
        p.stdout = responses[call_idx[0]]
        call_idx[0] += 1
        return p

    monkeypatch.setattr(subprocess, "run", fake_run)

    votes = [g._factcheck("some answer", "ground truth", "m") for _ in range(3)]
    yes = sum(1 for v in votes if v is True)
    majority = yes > len(votes) / 2
    assert majority is False


def test_factcheck_unparseable_counts_as_no(monkeypatch):
    """Unparseable response -> None (counts as NO in majority vote).

    YES/"maybe"/NO -> yes=1, majority False (1 > 1.5 is False).
    """
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    responses = ["YES", "maybe", "NO"]
    call_idx = [0]

    class _P:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kw):
        p = _P()
        p.stdout = responses[call_idx[0]]
        call_idx[0] += 1
        return p

    monkeypatch.setattr(subprocess, "run", fake_run)

    votes = [g._factcheck("some answer", "ground truth", "m") for _ in range(3)]
    # "maybe" should parse as None
    assert votes[1] is None
    yes = sum(1 for v in votes if v is True)
    majority = yes > len(votes) / 2
    assert majority is False


# ──────────────────────────────────────────────────────────────────────────────
# _answer tests
# ──────────────────────────────────────────────────────────────────────────────


def test_empty_answer_skips_factcheck(monkeypatch, tmp_path: Path):
    """When _answer returns "" (all attempts empty), _factcheck must NOT be called."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(g, "build_context_prefix", _bcp)
    monkeypatch.setattr(g, "MemoryStore", _Mem)

    # All subprocess.run calls return empty stdout (forces _answer to return "").
    class _EmptyP:
        returncode = 0
        stdout = ""

    factcheck_mock = MagicMock(return_value=None)
    monkeypatch.setattr(g, "_factcheck", factcheck_mock)

    # Patch subprocess.run so _answer always gets empty output.
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _EmptyP())

    # Write a minimal probes file with one probe.
    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "none",
            "--trials",
            "1",
            "--judge-models",
            "m1,m2,m3",
        ]
    )

    assert rc == 0
    # _factcheck must not have been called for the empty-answer probe.
    assert factcheck_mock.call_count == 0


def test_answer_retry_empty_then_good_two_calls(monkeypatch):
    """subprocess returns empty then good -> exactly 2 subprocess.run calls."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")

    call_count = [0]

    class _P:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kw):
        call_count[0] += 1
        p = _P()
        p.stdout = "good answer" if call_count[0] >= 2 else ""
        return p

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = g._answer("", "Q?", "m")
    assert result == "good answer"
    assert call_count[0] == 2


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation / end-to-end tests
# ──────────────────────────────────────────────────────────────────────────────


def test_accuracy_aggregation_half(monkeypatch, tmp_path: Path):
    """2 probes, 1 majority-True of 2 -> accuracy 0.5; n == 2 (trials=1)."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(g, "build_context_prefix", _bcp)
    monkeypatch.setattr(g, "MemoryStore", _Mem)

    # Probe 1: YES/YES/NO -> majority True; Probe 2: NO/NO/YES -> majority False.
    judge_seq = ["YES", "YES", "NO", "NO", "NO", "YES"]
    answer_seq = ["answer1", "answer2"]
    judge_call = [0]
    answer_call = [0]

    class _JP:
        returncode = 0
        stdout = ""

    def fake_answer(prefix, question, model):
        idx = answer_call[0] % len(answer_seq)
        answer_call[0] += 1
        return answer_seq[idx]

    def fake_run(cmd, **kw):
        p = _JP()
        p.stdout = judge_seq[judge_call[0] % len(judge_seq)]
        judge_call[0] += 1
        return p

    monkeypatch.setattr(g, "_answer", fake_answer)
    monkeypatch.setattr(subprocess, "run", fake_run)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(
        json.dumps(
            [
                {"id": "p1", "question": "Q1?", "ground_truth": "GT1"},
                {"id": "p2", "question": "Q2?", "ground_truth": "GT2"},
            ]
        )
    )
    out_file = tmp_path / "out.json"

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "none",
            "--trials",
            "1",
            "--judge-models",
            "m1,m2,m3",
            "--out",
            str(out_file),
        ]
    )

    assert rc == 0
    data = json.loads(out_file.read_text())
    arm = data["arms"]["none"]
    assert arm["n"] == 2
    assert abs(arm["accuracy"] - 0.5) < 1e-9


def test_accuracy_delta_vs_none_present_and_correct(monkeypatch, tmp_path: Path):
    """When 'none' arm is present, accuracy_delta_vs_none is populated and correct."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(g, "build_context_prefix", _bcp)
    monkeypatch.setattr(g, "MemoryStore", _Mem)

    # none arm: 1/1 correct (YES/YES/NO -> majority True)
    # wiki arm: 0/1 correct (NO/NO/YES -> majority False)
    responses_by_arm: dict[str, list[str]] = {
        "none": ["YES", "YES", "NO"],
        "wiki": ["NO", "NO", "YES"],
    }
    arm_call: dict[str, int] = {"none": 0, "wiki": 0}
    current_arm: list[str] = []

    class _P:
        returncode = 0
        stdout = ""

    def fake_bcp(root, mem, query, **kw):
        # Determine arm from include_layers kwarg.
        inc = kw.get("include_layers")
        if inc is None or inc == g._LAYERS_MAP["none"]:
            current_arm[:] = ["none"]
        else:
            current_arm[:] = ["wiki"]
        return ""

    def fake_run(cmd, **kw):
        arm = current_arm[0] if current_arm else "none"
        idx = arm_call[arm]
        arm_call[arm] += 1
        responses = responses_by_arm[arm]
        p = _P()
        p.stdout = responses[idx % len(responses)]
        return p

    def fake_answer(prefix, question, model):
        return "some answer"

    monkeypatch.setattr(g, "build_context_prefix", fake_bcp)
    monkeypatch.setattr(g, "_answer", fake_answer)
    monkeypatch.setattr(subprocess, "run", fake_run)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))
    out_file = tmp_path / "out.json"

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "none",
            "wiki",
            "--trials",
            "1",
            "--judge-models",
            "m1,m2,m3",
            "--out",
            str(out_file),
        ]
    )

    assert rc == 0
    data = json.loads(out_file.read_text())
    assert "accuracy_delta_vs_none" in data
    delta = data["accuracy_delta_vs_none"]
    arms = data["arms"]
    for arm_name in ("none", "wiki"):
        expected = round(arms[arm_name]["accuracy"] - arms["none"]["accuracy"], 3)
        assert delta[arm_name] == expected


def test_arm_prefix_uses_layers_map(monkeypatch, tmp_path: Path):
    """build_context_prefix is called with include_layers == _LAYERS_MAP[arm] per arm."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(g, "MemoryStore", _Mem)

    seen_layers: list = []

    def recording_bcp(root, mem, query, **kw):
        seen_layers.append(kw.get("include_layers"))
        return ""

    monkeypatch.setattr(g, "build_context_prefix", recording_bcp)

    # Stub _answer so no subprocess needed.
    monkeypatch.setattr(g, "_answer", lambda p, q, m: "ans")

    # Stub _factcheck so no subprocess needed.
    monkeypatch.setattr(g, "_factcheck", lambda a, gt, m: True)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "none",
            "wiki",
            "--trials",
            "1",
            "--judge-models",
            "m1",
        ]
    )

    assert rc == 0
    assert g._LAYERS_MAP["none"] in seen_layers
    assert g._LAYERS_MAP["wiki"] in seen_layers


# ──────────────────────────────────────────────────────────────────────────────
# _retrieve_wiki tests — real temp FTS5 corpus; no subprocess
# ──────────────────────────────────────────────────────────────────────────────


def test_retrieve_wiki_ranks_match_first(tmp_path: Path):
    """doc with unique query terms ranks first; result <=k and non-empty."""
    (tmp_path / "a.md").write_text("apples and oranges in a fruit basket")
    (tmp_path / "b.md").write_text("the quantum chromodynamics gluon lagrangian")
    (tmp_path / "c.md").write_text("weather forecast rain tomorrow")

    results = g._retrieve_wiki(tmp_path, "gluon chromodynamics", 3)

    assert results, "expected non-empty results"
    assert len(results) <= 3
    assert results[0][0].endswith("b.md"), f"expected b.md first, got {results[0][0]}"


def test_retrieve_wiki_respects_k(tmp_path: Path):
    """k=2 caps results even when more docs match."""
    for i in range(5):
        (tmp_path / f"doc{i}.md").write_text(f"common keyword document {i}")

    results = g._retrieve_wiki(tmp_path, "common keyword", 2)

    assert len(results) <= 2


def test_retrieve_wiki_missing_and_empty_dir(tmp_path: Path):
    """Missing dir -> []; real but empty dir -> []."""
    assert g._retrieve_wiki(tmp_path / "nope", "q", 3) == []

    empty = tmp_path / "empty_wiki"
    empty.mkdir()
    assert g._retrieve_wiki(empty, "q", 3) == []


def test_retrieve_wiki_nonsense_query_never_raises(tmp_path: Path):
    """Special-char query and empty query both return a list and do not raise."""
    (tmp_path / "doc.md").write_text("some content about things")

    result1 = g._retrieve_wiki(tmp_path, 'foo "bar" AND baz! OR (qux)', 3)
    assert isinstance(result1, list)
    assert len(result1) <= 3

    result2 = g._retrieve_wiki(tmp_path, "", 3)
    assert isinstance(result2, list)
    assert len(result2) <= 3


# ──────────────────────────────────────────────────────────────────────────────
# _sanitize_fts_query tests
# ──────────────────────────────────────────────────────────────────────────────


def test_sanitize_fts_query_handles_special_chars():
    """Sanitized string does not raise and executes against a real in-memory FTS5 table."""
    import sqlite3

    raw = 'foo "bar" AND baz!'
    safe = g._sanitize_fts_query(raw)

    assert isinstance(safe, str), "must return a string"

    # Confirm MATCH with the sanitized string executes without OperationalError.
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(content, tokenize='porter unicode61')")
    conn.execute("INSERT INTO t (content) VALUES (?)", ("foo bar baz sample text",))
    # Should not raise.
    rows = conn.execute("SELECT content FROM t WHERE t MATCH ?", (safe,)).fetchall()
    conn.close()
    assert isinstance(rows, list)


# ──────────────────────────────────────────────────────────────────────────────
# wikirag arm integration tests
# ──────────────────────────────────────────────────────────────────────────────


def test_wikirag_arm_records_retrieved_and_skips_bcp(monkeypatch, tmp_path: Path):
    """wikirag arm records retrieved paths; build_context_prefix is NOT called."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    monkeypatch.setattr(g, "_retrieve_wiki", lambda d, q, k: [("/w/article1.md", "ctx body")])

    bcp_mock = MagicMock(return_value="")
    monkeypatch.setattr(g, "build_context_prefix", bcp_mock)
    monkeypatch.setattr(g, "_answer", lambda p, q, m: "ans")
    monkeypatch.setattr(g, "_factcheck", lambda a, gt, m: True)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))
    out_file = tmp_path / "out.json"

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "wikirag",
            "--wiki-dir",
            str(wiki_dir),
            "--trials",
            "1",
            "--judge-models",
            "m1",
            "--out",
            str(out_file),
        ]
    )

    assert rc == 0
    data = json.loads(out_file.read_text())
    per_probe = data["arms"]["wikirag"]["per_probe"]
    assert per_probe[0]["retrieved"] == ["/w/article1.md"]
    assert per_probe[0]["majority"] is True
    assert bcp_mock.call_count == 0, "build_context_prefix must NOT be called for wikirag arm"


def test_wikirag_no_dir_clear_message_no_subprocess(monkeypatch, tmp_path: Path, capsys):
    """wikirag-only without --wiki-dir: rc!=0, zero subprocess calls, message mentions wiki-dir."""
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)
    monkeypatch.setattr(g, "MemoryStore", _Mem)
    monkeypatch.setattr(g, "build_context_prefix", _bcp)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "wikirag",
            "--trials",
            "1",
            "--judge-models",
            "m1",
        ]
    )

    assert rc != 0
    assert run_mock.call_count == 0
    out = capsys.readouterr().out
    assert "wiki-dir" in out, f"expected 'wiki-dir' in output, got: {out!r}"


# ──────────────────────────────────────────────────────────────────────────────
# wikivec arm tests — injected fake embed_fn; no fastembed/network
# ──────────────────────────────────────────────────────────────────────────────

try:
    import sqlite_vec  # noqa: F401

    _HAS_VEC = True
except Exception:
    _HAS_VEC = False


def _fake_embed_factory(keyword: str, match_vec: list[float], default_vec: list[float]):
    """Return a fake embed_fn that maps texts containing keyword to match_vec, others to default_vec."""

    def embed_fn(texts: list[str]) -> list[list[float]]:
        result = []
        for t in texts:
            result.append(match_vec[:] if keyword in t else default_vec[:])
        return result

    return embed_fn


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_retrieve_vec_ranks_semantic_match_first(tmp_path: Path):
    """Fake embed_fn maps compliance doc + query to same vector; compliance doc ranks first."""
    (tmp_path / "compliance.md").write_text("compliance audit requirements regulatory framework")
    (tmp_path / "producer.md").write_text("producer throughput acks lz4 compression settings")
    (tmp_path / "consumer.md").write_text("consumer group rebalance offset commit strategy")

    # compliance doc and query share [1,0,0,0]; others get [0,1,0,0] (far away by L2)
    embed_fn = _fake_embed_factory("compliance", [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])

    results = g._retrieve_vec(tmp_path, "compliance audit query", 3, embed_fn)

    assert results, "expected non-empty results"
    assert len(results) <= 3
    assert results[0][0].endswith("compliance.md"), (
        f"expected compliance.md first, got {results[0][0]}"
    )


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_retrieve_vec_respects_k(tmp_path: Path):
    """k=2 caps results even when more docs exist."""
    for i in range(5):
        (tmp_path / f"doc{i}.md").write_text(f"common content document number {i}")

    embed_fn = _fake_embed_factory("common", [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0])
    results = g._retrieve_vec(tmp_path, "common content query", 2, embed_fn)

    assert len(results) <= 2


def test_retrieve_vec_missing_and_empty_dir(tmp_path: Path):
    """Missing dir -> []; empty dir -> []; blank query -> []."""
    embed_fn = _fake_embed_factory("x", [1.0, 0.0], [0.0, 1.0])

    assert g._retrieve_vec(tmp_path / "nope", "q", 3, embed_fn) == []

    empty = tmp_path / "empty_wiki"
    empty.mkdir()
    assert g._retrieve_vec(empty, "q", 3, embed_fn) == []

    (tmp_path / "doc.md").write_text("some content")
    assert g._retrieve_vec(tmp_path, "", 3, embed_fn) == []


def test_retrieve_vec_never_raises_on_bad_embed_fn(tmp_path: Path):
    """embed_fn that raises -> returns [] (does not propagate exception)."""
    (tmp_path / "doc.md").write_text("some content")

    def bad_embed_fn(texts):
        raise RuntimeError("embedding service unavailable")

    result = g._retrieve_vec(tmp_path, "query", 3, bad_embed_fn)
    assert result == []


@pytest.mark.skipif(not _HAS_VEC, reason="sqlite_vec not installed")
def test_wikivec_arm_records_retrieved_and_skips_bcp(monkeypatch, tmp_path: Path):
    """wikivec arm records retrieved paths; build_context_prefix NOT called; embed_model in output."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    monkeypatch.setattr(g, "_retrieve_vec", lambda d, q, k, fn: [("/w/x.md", "wiki body")])
    monkeypatch.setattr(g, "_default_embedder", lambda model: lambda texts: [[1.0, 0.0]])

    bcp_mock = MagicMock(return_value="")
    monkeypatch.setattr(g, "build_context_prefix", bcp_mock)
    monkeypatch.setattr(g, "_answer", lambda p, q, m: "ans")
    monkeypatch.setattr(g, "_factcheck", lambda a, gt, m: True)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))
    out_file = tmp_path / "out.json"

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "wikivec",
            "--wiki-dir",
            str(wiki_dir),
            "--trials",
            "1",
            "--judge-models",
            "m1",
            "--out",
            str(out_file),
        ]
    )

    assert rc == 0
    data = json.loads(out_file.read_text())
    per_probe = data["arms"]["wikivec"]["per_probe"]
    assert per_probe[0]["retrieved"] == ["/w/x.md"]
    assert per_probe[0]["majority"] is True
    assert bcp_mock.call_count == 0, "build_context_prefix must NOT be called for wikivec arm"
    assert "embed_model" in data


def test_wikivec_no_dir_clear_message_no_subprocess(monkeypatch, tmp_path: Path, capsys):
    """wikivec-only without --wiki-dir: rc!=0, zero subprocess calls, message mentions wiki-dir."""
    run_mock = MagicMock()
    monkeypatch.setattr("subprocess.run", run_mock)
    monkeypatch.setattr(g, "MemoryStore", _Mem)
    monkeypatch.setattr(g, "build_context_prefix", _bcp)

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "wikivec",
            "--trials",
            "1",
            "--judge-models",
            "m1",
        ]
    )

    assert rc != 0
    assert run_mock.call_count == 0
    out = capsys.readouterr().out
    assert "wiki-dir" in out, f"expected 'wiki-dir' in output, got: {out!r}"


def test_default_embedder_raises_when_fastembed_missing(monkeypatch):
    """_default_embedder raises RuntimeError when fastembed import fails."""
    import builtins

    real_import = builtins.__import__

    def patched_import(name, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("No module named 'fastembed'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", patched_import)

    # Remove cached module if present so our patched import is triggered.
    import sys

    sys.modules.pop("fastembed", None)

    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="fastembed"):
        g._default_embedder("any-model")


def test_default_embedder_unavailable_degrades_gracefully(monkeypatch, tmp_path: Path, capsys):
    """When _default_embedder raises, wikivec arm is skipped; other arms still produce records."""
    monkeypatch.setattr(
        g,
        "_default_embedder",
        lambda m: (_ for _ in ()).throw(RuntimeError("fastembed not found")),
    )
    monkeypatch.setattr(g, "build_context_prefix", _bcp)
    monkeypatch.setattr(g, "MemoryStore", _Mem)
    monkeypatch.setattr(g, "_answer", lambda p, q, m: "ans")
    monkeypatch.setattr(g, "_factcheck", lambda a, gt, m: True)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps([{"id": "p1", "question": "Q?", "ground_truth": "GT"}]))

    rc = g.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--layers",
            "wikivec",
            "none",
            "--wiki-dir",
            str(wiki_dir),
            "--trials",
            "1",
            "--judge-models",
            "m1",
        ]
    )

    assert rc == 0, "harness must not crash when fastembed is unavailable"
    out = capsys.readouterr().out
    assert "wikivec arm unavailable" in out, f"expected degradation message, got: {out!r}"


# ──────────────────────────────────────────────────────────────────────────────
# RGB helpers — Task 1 tests (all offline; no claude binary / network)
# ──────────────────────────────────────────────────────────────────────────────

_RGB_PROBES_FIXTURE = [
    {
        "id": "p1",
        "question": "What is the default replication factor for Confluent Cloud?",
        "ground_truth": "3",
        "gold": "Confluent Cloud uses a default replication factor of 3 for all topics.",
    },
    {
        "id": "p2",
        "question": "What compression codec does Confluent recommend for throughput?",
        "ground_truth": "lz4",
        "gold": [
            "lz4 compression is recommended for high-throughput Kafka producers.",
            "zstd is preferred when storage efficiency matters more than CPU cost.",
        ],
    },
    {
        "id": "p3",
        "question": "Which consumer setting should be disabled in processing workloads?",
        "ground_truth": "enable.auto.commit",
        # No gold — intentionally absent to test skips
        "counterfactual": "Confluent recommends always enabling auto-commit for simplicity.",
        "wrong_answer": "enable.auto.commit should be enabled",
    },
    {
        "id": "p4",
        "question": "What is the recommended acks setting for durable producers?",
        "ground_truth": "all",
        "gold": "Producers must use acks=all for durable, loss-free delivery.",
    },
]


def test_rgb_distractors_excludes_self_deterministic_and_count():
    """_rgb_distractors returns gold from OTHER probes, excludes self, is deterministic."""
    probes = _RGB_PROBES_FIXTURE
    # p1 has string gold, p2 has list gold (2 items), p3 has no gold, p4 has string gold
    # Distractors for p1: gold from p2 (2 items) + p4 (1 item) => up to n=3 total
    result = g._rgb_distractors(probes[0], probes, n=5)
    # Must not include p1's own gold
    assert probes[0]["gold"] not in result
    # Must be deterministic
    result2 = g._rgb_distractors(probes[0], probes, n=5)
    assert result == result2
    # All returned items are strings
    assert all(isinstance(d, str) for d in result)
    # p3 has no gold, so result comes only from p2 and p4
    assert len(result) <= 3  # 2 from p2 list + 1 from p4

    # For p2 (multi-gold): distractors should be from p1 and p4 (not p3 which has no gold)
    result_p2 = g._rgb_distractors(probes[1], probes, n=10)
    assert probes[1]["gold"][0] not in result_p2
    assert probes[1]["gold"][1] not in result_p2

    # n=1 cap: only 1 distractor max
    result_capped = g._rgb_distractors(probes[0], probes, n=1)
    assert len(result_capped) <= 1


def test_rgb_noise_context_has_gold_and_floor_distractors(monkeypatch):
    """_rgb_noise: context has gold + floor(ratio*k) distractors; gold always present."""
    probes = _RGB_PROBES_FIXTURE
    # p1 has string gold
    probe = probes[0]

    seen_prefixes = []

    def fake_answer(prefix, question, model, *, instruction="Answer concisely and specifically."):
        seen_prefixes.append(prefix)
        return "3"

    def fake_factcheck(answer, ground_truth, model):
        return True

    monkeypatch.setattr(g, "_answer", fake_answer)
    monkeypatch.setattr(g, "_factcheck", fake_factcheck)

    result = g._rgb_noise(probe, probes, noise_ratio=0.4, k=5, answer_model="m", judge_models=["m"])
    assert result is not None
    assert result["probe_id"] == "p1"
    assert "noise_ratio" in result
    assert "n_distractors" in result
    assert "majority" in result
    # floor(0.4 * 5) == 2 distractors
    assert result["n_distractors"] == 2
    # Gold must be present in the prefix
    assert len(seen_prefixes) == 1
    assert probe["gold"] in seen_prefixes[0]


def test_rgb_negative_excludes_gold_and_scores_rejection(monkeypatch):
    """_rgb_negative: context has NO gold; rejection scored via fast-path then judge."""
    probes = _RGB_PROBES_FIXTURE
    probe = probes[0]

    seen_prefixes = []

    def fake_answer(prefix, question, model, *, instruction="Answer concisely and specifically."):
        seen_prefixes.append(prefix)
        # Simulate a refusal — fast-path should catch "cannot answer"
        return "I cannot answer due to insufficient information."

    monkeypatch.setattr(g, "_answer", fake_answer)
    # _judge_rejection should NOT be called (regex fast-path handles refusal)
    judge_mock = MagicMock(return_value=True)
    monkeypatch.setattr(g, "_judge_rejection", judge_mock)

    result = g._rgb_negative(probe, probes, k=3, answer_model="m", judge_models=["m"])
    assert result is not None
    assert result["probe_id"] == "p1"
    assert "rejected" in result
    assert result["rejected"] is True
    # Gold must NOT be in the context prefix
    assert len(seen_prefixes) == 1
    if probe.get("gold"):
        gold = probe["gold"]
        if isinstance(gold, str):
            assert gold not in seen_prefixes[0]

    # Fall-through case: non-refusal answer goes to _judge_rejection
    def fake_answer_norefuse(
        prefix, question, model, *, instruction="Answer concisely and specifically."
    ):
        return "The answer is 3."

    monkeypatch.setattr(g, "_answer", fake_answer_norefuse)
    monkeypatch.setattr(g, "_judge_rejection", lambda a, m: False)

    result2 = g._rgb_negative(probe, probes, k=3, answer_model="m", judge_models=["m"])
    assert result2 is not None
    assert result2["rejected"] is False


def test_rgb_integration_requires_two_gold_else_none(monkeypatch):
    """_rgb_integration: returns None for probes with <2 gold passages."""
    probes = _RGB_PROBES_FIXTURE

    monkeypatch.setattr(
        g, "_answer", lambda p, q, m, *, instruction="Answer concisely and specifically.": "lz4"
    )
    monkeypatch.setattr(g, "_factcheck", lambda a, gt, m: True)

    # p2 has list gold with 2 items => should run
    result_multi = g._rgb_integration(probes[1], probes, k=5, answer_model="m", judge_models=["m"])
    assert result_multi is not None
    assert result_multi["probe_id"] == "p2"
    assert "majority" in result_multi

    # p1 has string gold (not a list of >=2) => skip
    result_single = g._rgb_integration(probes[0], probes, k=5, answer_model="m", judge_models=["m"])
    assert result_single is None

    # p3 has no gold => skip
    result_none = g._rgb_integration(probes[2], probes, k=5, answer_model="m", judge_models=["m"])
    assert result_none is None


def test_rgb_counterfactual_robust_vs_misled_and_none_when_missing(monkeypatch):
    """_rgb_counterfactual: returns robust/misled dict or None when fields missing."""
    probes = _RGB_PROBES_FIXTURE

    call_args = []

    def fake_factcheck(answer, ground_truth, model):
        call_args.append(ground_truth)
        # robust check: answer vs real ground_truth -> True
        # misled check: answer vs wrong_answer -> False
        return ground_truth == probes[2]["ground_truth"]

    monkeypatch.setattr(
        g,
        "_answer",
        lambda p, q, m, *, instruction="Answer concisely and specifically.": "enable.auto.commit",
    )
    monkeypatch.setattr(g, "_factcheck", fake_factcheck)

    # p3 has counterfactual + wrong_answer
    result = g._rgb_counterfactual(probes[2], answer_model="m", judge_models=["m"])
    assert result is not None
    assert result["probe_id"] == "p3"
    assert "robust" in result
    assert "misled" in result
    assert result["robust"] is True
    assert result["misled"] is False

    # p1 has no counterfactual/wrong_answer => None
    result_none = g._rgb_counterfactual(probes[0], answer_model="m", judge_models=["m"])
    assert result_none is None


def test_judge_rejection_regex_fastpath_no_subprocess(monkeypatch):
    """Common refusal phrases -> True via regex fast-path; subprocess.run NOT called."""
    run_mock = MagicMock()
    monkeypatch.setattr(subprocess, "run", run_mock)
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")

    refusals = [
        "I cannot answer this question.",
        "There is insufficient information to respond.",
        "I have no information about this topic.",
        "I don't know the answer to that.",
        "I am unable to provide that information.",
        "There is not enough context here.",
    ]
    for phrase in refusals:
        result = g._judge_rejection(phrase, "m")
        assert result is True, f"expected True for refusal phrase: {phrase!r}"

    assert run_mock.call_count == 0, "subprocess.run must NOT be called for fast-path refusals"


def test_answer_instruction_kwarg_default_is_byte_identical(monkeypatch):
    """_answer with no instruction kwarg produces the same prompt as before (byte-identical)."""
    monkeypatch.setattr(g, "_locate_claude", lambda: "/bin/claude")

    captured = []

    class _P:
        returncode = 0
        stdout = "answer"

    def fake_run(cmd, **kw):
        captured.append(cmd[-1])  # last arg is the prompt
        return _P()

    monkeypatch.setattr(subprocess, "run", fake_run)

    g._answer("ctx", "What is X?", "m")
    prompt_default = captured[-1]

    # The default should end with the old trailer
    assert prompt_default.endswith("\nAnswer concisely and specifically.")

    # With explicit instruction= same value -> identical
    captured.clear()
    g._answer("ctx", "What is X?", "m", instruction="Answer concisely and specifically.")
    assert captured[-1] == prompt_default

    # With different instruction -> different trailer
    captured.clear()
    g._answer("ctx", "What is X?", "m", instruction="Respond YES or NO only.")
    assert captured[-1].endswith("\nRespond YES or NO only.")
    assert not captured[-1].endswith("\nAnswer concisely and specifically.")
