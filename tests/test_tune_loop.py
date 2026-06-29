"""Tests for bench/tune_loop.py — all subprocess calls mocked; no live claude/network."""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import bench.tune_loop as t

# ──────────────────────────────────────────────────────────────────────────────
# Minimal stubs (mirror bench/grounding offline idiom)
# ──────────────────────────────────────────────────────────────────────────────


def _bcp(root, memory, query, **kw):
    """Stub build_context_prefix: returns empty prefix without touching disk."""
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
# Probe fixture
# ──────────────────────────────────────────────────────────────────────────────

_PROBES = [
    {"id": "p1", "question": "Q1?", "ground_truth": "GT1"},
    {"id": "p2", "question": "Q2?", "ground_truth": "GT2"},
    {"id": "p3", "question": "Q3?", "ground_truth": "GT3"},
]

_GATE_ADOPT = {
    "decision": "ADOPT_B",
    "delta": 0.2,
    "ci_overlap": False,
    "variant_a": {"accuracy": 0.6, "n": 5, "wilson_ci": [0.3, 0.9], "text_sha": "abc123"},
    "variant_b": {"accuracy": 0.8, "n": 5, "wilson_ci": [0.5, 1.0], "text_sha": "def456"},
}

_FAILURES = [
    {"id": "p1", "question": "Q1?", "ground_truth": "GT1", "answer": "wrong1"},
    {"id": "p2", "question": "Q2?", "ground_truth": "GT2", "answer": "wrong2"},
]


# ──────────────────────────────────────────────────────────────────────────────
# _mine_failures tests
# ──────────────────────────────────────────────────────────────────────────────


def test_mine_failures_returns_only_failing_probes(monkeypatch, tmp_path):
    """Probes with majority-False are failures; majority-True probes are NOT returned."""
    monkeypatch.setattr(t, "build_context_prefix", _bcp)
    monkeypatch.setattr(t, "MemoryStore", _Mem)

    # p1 -> majority True (YES/YES/NO), p2 -> majority False (NO/NO/YES), p3 -> majority True
    answers = {"p1": "A1", "p2": "A2", "p3": "A3"}
    votes_map = {
        "p1": [True, True, False],
        "p2": [False, False, True],
        "p3": [True, True, True],
    }
    call_idx: dict[str, int] = {"p1": 0, "p2": 0, "p3": 0}
    current_probe_id: list[str] = []

    def fake_answer(prefix, question, model, *, instruction="Answer concisely and specifically."):
        for p in _PROBES:
            if p["question"] == question:
                current_probe_id[:] = [p["id"]]
                break
        return answers[current_probe_id[0]]

    def fake_factcheck(answer, gt, model):
        pid = current_probe_id[0]
        idx = call_idx[pid]
        call_idx[pid] += 1
        return votes_map[pid][idx % len(votes_map[pid])]

    monkeypatch.setattr(t, "_answer", fake_answer)
    monkeypatch.setattr(t, "_factcheck", fake_factcheck)

    result = t._mine_failures(
        tmp_path, _PROBES, "Answer concisely.", "none", "sonnet", ["m1", "m2", "m3"]
    )
    ids = [r["id"] for r in result]
    assert "p2" in ids, "p2 (majority False) must be in failures"
    assert "p1" not in ids, "p1 (majority True) must not be in failures"
    assert "p3" not in ids, "p3 (majority True) must not be in failures"
    for rec in result:
        assert {"id", "question", "ground_truth", "answer"} <= set(rec.keys())


def test_mine_failures_empty_answer_all_none_votes_is_failure(monkeypatch, tmp_path):
    """Empty answer -> all-None votes -> yes_count=0 -> not majority -> failure recorded."""
    monkeypatch.setattr(t, "build_context_prefix", _bcp)
    monkeypatch.setattr(t, "MemoryStore", _Mem)
    monkeypatch.setattr(t, "_answer", lambda p, q, m, **kw: "")
    factcheck_mock = MagicMock(return_value=True)
    monkeypatch.setattr(t, "_factcheck", factcheck_mock)

    probes = [{"id": "p1", "question": "Q1?", "ground_truth": "GT1"}]
    result = t._mine_failures(tmp_path, probes, "instr", "none", "sonnet", ["m1", "m2", "m3"])
    assert len(result) == 1
    assert result[0]["id"] == "p1"
    # _factcheck must NOT be called for empty answers
    assert factcheck_mock.call_count == 0


def test_mine_failures_never_raises(monkeypatch, tmp_path):
    """If _answer raises, _mine_failures returns [] without propagating."""
    monkeypatch.setattr(t, "build_context_prefix", _bcp)
    monkeypatch.setattr(t, "MemoryStore", _Mem)
    monkeypatch.setattr(t, "_answer", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))

    result = t._mine_failures(tmp_path, _PROBES, "instr", "none", "sonnet", ["m1"])
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# _propose_candidate tests
# ──────────────────────────────────────────────────────────────────────────────


def test_propose_candidate_empty_failures_no_subprocess(monkeypatch):
    """Empty failures list -> None; subprocess.run is NOT called."""
    run_mock = MagicMock()
    monkeypatch.setattr(t.subprocess, "run", run_mock)
    result = t._propose_candidate("old instr", [], "sonnet")
    assert result is None
    assert run_mock.call_count == 0


def test_propose_candidate_returns_stripped_stdout_on_success(monkeypatch):
    """Happy path: _locate_claude returns binary, rc=0 -> stripped stdout returned."""
    monkeypatch.setattr(t, "_locate_claude", lambda: "/bin/claude")

    class _P:
        returncode = 0
        stdout = "  NEW INSTRUCTION  \n"

    monkeypatch.setattr(t.subprocess, "run", lambda *a, **kw: _P())
    result = t._propose_candidate(
        "base instr",
        [{"id": "p1", "question": "Q?", "ground_truth": "GT", "answer": "A"}],
        "sonnet",
    )
    assert result == "NEW INSTRUCTION"


def test_propose_candidate_rc_nonzero_returns_none(monkeypatch):
    """Non-zero subprocess rc -> None."""
    monkeypatch.setattr(t, "_locate_claude", lambda: "/bin/claude")

    class _P:
        returncode = 1
        stdout = "some output"

    monkeypatch.setattr(t.subprocess, "run", lambda *a, **kw: _P())
    result = t._propose_candidate(
        "base instr",
        [{"id": "p1", "question": "Q?", "ground_truth": "GT", "answer": "A"}],
        "sonnet",
    )
    assert result is None


def test_propose_candidate_no_claude_binary_returns_none(monkeypatch):
    """_locate_claude returns None -> None; no subprocess call."""
    monkeypatch.setattr(t, "_locate_claude", lambda: None)
    run_mock = MagicMock()
    monkeypatch.setattr(t.subprocess, "run", run_mock)
    result = t._propose_candidate(
        "base instr",
        [{"id": "p1", "question": "Q?", "ground_truth": "GT", "answer": "A"}],
        "sonnet",
    )
    assert result is None
    assert run_mock.call_count == 0


# ──────────────────────────────────────────────────────────────────────────────
# _gate tests
# ──────────────────────────────────────────────────────────────────────────────


def _write_gate_json(work_dir: Path, decision: str = "ADOPT_B") -> None:
    """Helper: write a minimal gate.json into work_dir."""
    gate_data = {
        "decision": decision,
        "delta": 0.2,
        "ci_overlap": False,
        "variant_a": {"accuracy": 0.6, "n": 5, "wilson_ci": [0.3, 0.9], "text_sha": "abc123"},
        "variant_b": {"accuracy": 0.8, "n": 5, "wilson_ci": [0.5, 1.0], "text_sha": "def456"},
    }
    (work_dir / "gate.json").write_text(json.dumps(gate_data))


def test_gate_happy_path(monkeypatch, tmp_path):
    """_gate writes instruction files, calls _run_promptab, returns parsed gate dict."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    def fake_run_promptab(ns, probes):
        _write_gate_json(work_dir)
        return 0

    monkeypatch.setattr(t, "_run_promptab", fake_run_promptab)

    result = t._gate(
        tmp_path,
        _PROBES,
        "base text",
        "candidate text",
        "none",
        "sonnet",
        "sonnet,sonnet,opus",
        2,
        work_dir,
    )
    assert result is not None
    assert result["decision"] == "ADOPT_B"
    assert (work_dir / "base_instruction.txt").read_text() == "base text"
    assert (work_dir / "candidate_instruction.txt").read_text() == "candidate text"


def test_gate_missing_gate_json_returns_none(monkeypatch, tmp_path):
    """If gate.json is not written, _gate returns None."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.setattr(t, "_run_promptab", lambda ns, probes: 1)
    result = t._gate(tmp_path, _PROBES, "base", "candidate", "none", "sonnet", "m1", 1, work_dir)
    assert result is None


def test_gate_unparseable_gate_json_returns_none(monkeypatch, tmp_path):
    """Unparseable gate.json -> None."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    def fake_run_promptab(ns, probes):
        (work_dir / "gate.json").write_text("not valid json {{{")
        return 0

    monkeypatch.setattr(t, "_run_promptab", fake_run_promptab)
    result = t._gate(tmp_path, _PROBES, "base", "candidate", "none", "sonnet", "m1", 1, work_dir)
    assert result is None


def test_gate_judge_models_comma_string_to_ns(monkeypatch, tmp_path):
    """_gate passes judge_models as a raw comma STRING to the SimpleNamespace (not split list)."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    captured_ns: list = []

    def fake_run_promptab(ns, probes):
        captured_ns.append(ns)
        _write_gate_json(work_dir)
        return 0

    monkeypatch.setattr(t, "_run_promptab", fake_run_promptab)
    t._gate(tmp_path, _PROBES, "base", "candidate", "none", "sonnet", "m1,m2,m3", 2, work_dir)
    assert len(captured_ns) == 1
    # Must be the raw comma string, not a list
    assert captured_ns[0].judge_models == "m1,m2,m3"
    assert isinstance(captured_ns[0].judge_models, str)


# ──────────────────────────────────────────────────────────────────────────────
# _emit_report tests
# ──────────────────────────────────────────────────────────────────────────────


def test_emit_report_adopt_b_creates_json_and_md(tmp_path):
    """ADOPT_B gate -> tune_report.json and tune_report.md with correct fields."""
    work_dir = tmp_path / "run"
    work_dir.mkdir()
    report_path = t._emit_report(
        work_dir, "base instr", "candidate instr", _FAILURES, _GATE_ADOPT, "none"
    )

    assert (work_dir / "tune_report.json").exists()
    assert (work_dir / "tune_report.md").exists()

    data = json.loads((work_dir / "tune_report.json").read_text())
    assert "decision" in data
    assert "base_sha" in data
    assert "candidate_sha" in data
    assert "n_failures" in data
    assert "failure_ids" in data
    assert "candidate_instruction" in data
    assert data["decision"] == "ADOPT_B"
    assert data["n_failures"] == 2
    assert data["failure_ids"] == ["p1", "p2"]
    assert data["candidate_instruction"] == "candidate instr"
    assert report_path == work_dir / "tune_report.md"


def test_emit_report_no_candidate_decision_in_json(tmp_path):
    """gate=None -> decision == 'NO_CANDIDATE' in json."""
    work_dir = tmp_path / "run"
    work_dir.mkdir()
    t._emit_report(work_dir, "base instr", "", [], None, "none")
    data = json.loads((work_dir / "tune_report.json").read_text())
    assert data["decision"] == "NO_CANDIDATE"


def test_emit_report_disclaimer_exact_substring_in_md(tmp_path):
    """The exact disclaimer must appear verbatim in tune_report.md."""
    work_dir = tmp_path / "run"
    work_dir.mkdir()
    t._emit_report(work_dir, "base instr", "cand instr", _FAILURES, _GATE_ADOPT, "none")
    md_text = (work_dir / "tune_report.md").read_text()
    assert (
        "This tool does not modify any source files. Apply manually after human review." in md_text
    )


def test_emit_report_md_contains_does_not_modify(tmp_path):
    """Weaker check: md must contain the key phrase 'does not modify any source files'."""
    work_dir = tmp_path / "run"
    work_dir.mkdir()
    t._emit_report(work_dir, "base instr", "cand instr", _FAILURES, _GATE_ADOPT, "none")
    md_text = (work_dir / "tune_report.md").read_text()
    assert "does not modify any source files" in md_text


# ──────────────────────────────────────────────────────────────────────────────
# run_tune_loop end-to-end tests
# ──────────────────────────────────────────────────────────────────────────────


def _make_run_args(tmp_path: Path, probes_file: Path | None = None, out_dir: Path | None = None):
    """Build a minimal args SimpleNamespace for run_tune_loop."""
    if probes_file is None:
        probes_file = tmp_path / "probes.json"
        probes_file.write_text(json.dumps(_PROBES))
    return types.SimpleNamespace(
        root=tmp_path,
        probes=probes_file,
        base_instruction=None,
        arm="none",
        answer_model="sonnet",
        judge_models="sonnet,sonnet,opus",
        trials=2,
        out_dir=out_dir or (tmp_path / "out"),
    )


def test_run_tune_loop_happy_path_returns_0(monkeypatch, tmp_path):
    """Full happy path: failures -> candidate -> gate -> report; rc 0, out_dir created."""
    monkeypatch.setattr(t, "_load_probes", lambda p: _PROBES)
    monkeypatch.setattr(t, "_read_variant", lambda p: "base instruction")
    monkeypatch.setattr(t, "_mine_failures", lambda *a, **kw: _FAILURES)
    monkeypatch.setattr(t, "_propose_candidate", lambda *a, **kw: "candidate instruction")
    monkeypatch.setattr(t, "_gate", lambda *a, **kw: _GATE_ADOPT)

    args = _make_run_args(tmp_path)
    rc = t.run_tune_loop(args)
    assert rc == 0
    assert args.out_dir.exists()


def test_run_tune_loop_no_failures_emits_no_candidate_report(monkeypatch, tmp_path):
    """No failures -> NO_CANDIDATE report written, rc 0."""
    monkeypatch.setattr(t, "_load_probes", lambda p: _PROBES)
    monkeypatch.setattr(t, "_read_variant", lambda p: "base instruction")
    monkeypatch.setattr(t, "_mine_failures", lambda *a, **kw: [])

    args = _make_run_args(tmp_path)
    rc = t.run_tune_loop(args)
    assert rc == 0
    data = json.loads((args.out_dir / "tune_report.json").read_text())
    assert data["decision"] == "NO_CANDIDATE"


def test_run_tune_loop_none_candidate_emits_no_candidate_report(monkeypatch, tmp_path):
    """_propose_candidate -> None -> NO_CANDIDATE report, rc 0."""
    monkeypatch.setattr(t, "_load_probes", lambda p: _PROBES)
    monkeypatch.setattr(t, "_read_variant", lambda p: "base instruction")
    monkeypatch.setattr(t, "_mine_failures", lambda *a, **kw: _FAILURES)
    monkeypatch.setattr(t, "_propose_candidate", lambda *a, **kw: None)

    args = _make_run_args(tmp_path)
    rc = t.run_tune_loop(args)
    assert rc == 0
    data = json.loads((args.out_dir / "tune_report.json").read_text())
    assert data["decision"] == "NO_CANDIDATE"


def test_run_tune_loop_unreadable_probes_returns_1(monkeypatch, tmp_path):
    """_load_probes -> None -> rc 1."""
    monkeypatch.setattr(t, "_load_probes", lambda p: None)
    args = _make_run_args(tmp_path)
    rc = t.run_tune_loop(args)
    assert rc == 1


def test_run_tune_loop_never_raises_on_mine_failures_exception(monkeypatch, tmp_path):
    """If _mine_failures raises, run_tune_loop returns 1 without propagating."""
    monkeypatch.setattr(t, "_load_probes", lambda p: _PROBES)
    monkeypatch.setattr(t, "_read_variant", lambda p: "base instruction")
    monkeypatch.setattr(
        t, "_mine_failures", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    args = _make_run_args(tmp_path)
    rc = t.run_tune_loop(args)
    assert rc == 1


# ──────────────────────────────────────────────────────────────────────────────
# CRITICAL: no-source-writes guard
# ──────────────────────────────────────────────────────────────────────────────


def test_no_flowstate_writes_guard(monkeypatch, tmp_path):
    """Happy path must never write any file under a 'flowstate/' path segment."""
    monkeypatch.setattr(t, "_load_probes", lambda p: _PROBES)
    monkeypatch.setattr(t, "_read_variant", lambda p: "base instruction")
    monkeypatch.setattr(t, "_mine_failures", lambda *a, **kw: _FAILURES)
    monkeypatch.setattr(t, "_propose_candidate", lambda *a, **kw: "candidate instruction")
    monkeypatch.setattr(t, "_gate", lambda *a, **kw: _GATE_ADOPT)

    out_dir = tmp_path / "run"
    args = _make_run_args(tmp_path, out_dir=out_dir)
    rc = t.run_tune_loop(args)
    assert rc == 0

    # Walk every file created under tmp_path and assert none is under a flowstate/ segment.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "flowstate" not in path.parts, (
                f"Illegal write: file found under a 'flowstate/' segment: {path}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# main / _build_parser tests
# ──────────────────────────────────────────────────────────────────────────────


def test_main_passes_through_run_tune_loop_rc(monkeypatch, tmp_path):
    """main delegates to run_tune_loop and returns its rc (sentinel 42 pass-through)."""
    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps(_PROBES))
    out_dir = tmp_path / "r"

    monkeypatch.setattr(t, "run_tune_loop", lambda args: 42)

    rc = t.main(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 42


def test_build_parser_exposes_all_required_flags(tmp_path):
    """_build_parser must expose --root/--probes/--base-instruction/--arm/--answer-model/--judge-models/--trials/--out-dir."""
    parser = t._build_parser()
    probes_file = tmp_path / "probes.json"
    probes_file.write_text(json.dumps(_PROBES))
    args = parser.parse_args(
        [
            "--root",
            str(tmp_path),
            "--probes",
            str(probes_file),
            "--base-instruction",
            str(tmp_path / "instr.txt"),
            "--arm",
            "pack",
            "--answer-model",
            "opus",
            "--judge-models",
            "m1,m2",
            "--trials",
            "5",
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert args.root == tmp_path
    assert args.probes == probes_file
    assert args.base_instruction == tmp_path / "instr.txt"
    assert args.arm == "pack"
    assert args.answer_model == "opus"
    assert args.judge_models == "m1,m2"
    assert args.trials == 5
    assert args.out_dir == tmp_path / "out"
