"""Tests for bench/grounding.py — all subprocess calls mocked; no live claude."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

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
