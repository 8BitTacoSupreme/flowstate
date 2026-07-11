"""Offline tests for bench/ground.py — one-time auto-derived repo grounding.

The derivation ``ClaudeBridge`` call and the repomix pack are both mocked; no real
``claude`` CLI or ``repomix`` binary runs. Covers: interview is derived + persisted
to flowstate.json, run_pack is invoked, repomix-absent fails loud, the CLI entry
returns 0, and (Task 3) scaffold(synthetic=False) preserves the grounded state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import bench.ground as ground
from flowstate.bridge import BridgeResult
from flowstate.pack import PackResult
from flowstate.state import load_state


def _derivation() -> BridgeResult:
    """A successful derivation bridge result carrying STRICT JSON on .output."""
    payload = {
        "core_problem": "support engineers drown in multi-channel context",
        "ten_x_vision": "every support reply is context-complete on the first pass",
        "architecture_pattern": "event-driven multi-channel orchestrator",
        "milestones": ["ingest channels", "context assembly", "reply drafting"],
        "research_focus": "vector retrieval, channel adapters, prompt caching",
    }
    return BridgeResult(success=True, output=json.dumps(payload), exit_code=0)


def _install_stub_bridge(monkeypatch, result: BridgeResult) -> dict:
    """Patch ground.ClaudeBridge with a stub whose .run() returns ``result``.

    Returns a dict recording call counts so tests can assert one derivation call.
    """
    calls = {"run": 0}

    class _StubBridge:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args, **kwargs):
            calls["run"] += 1
            return result

    monkeypatch.setattr(ground, "ClaudeBridge", _StubBridge)
    return calls


def _install_pack_ok(monkeypatch, root: Path) -> dict:
    """Patch run_pack + _find_repomix so no real repomix runs. Records calls."""
    calls = {"pack": 0}

    def _fake_pack(r, **kwargs):
        calls["pack"] += 1
        return PackResult(success=True, output_path=Path(r) / "pack.xml", exit_code=0)

    monkeypatch.setattr(ground, "run_pack", _fake_pack)
    monkeypatch.setattr(ground, "_find_repomix", lambda: "/usr/bin/repomix")
    return calls


def _write_readme(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# FloxBot\n\nMulti-channel support system.\n")


def test_ground_from_repo_populates_interview(tmp_path: Path, monkeypatch):
    """ground_from_repo writes a non-empty interview into flowstate.json."""
    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, _derivation())
    _install_pack_ok(monkeypatch, tmp_path)

    ground.ground_from_repo(tmp_path)

    state = load_state(tmp_path)
    assert state.interview.research_focus == "vector retrieval, channel adapters, prompt caching"
    assert "support engineers" in state.interview.core_problem
    assert state.interview.milestones == ["ingest channels", "context assembly", "reply drafting"]


def test_ground_from_repo_runs_pack_once(tmp_path: Path, monkeypatch):
    """The repomix pack is invoked exactly once, after the single derivation call."""
    _write_readme(tmp_path)
    bridge_calls = _install_stub_bridge(monkeypatch, _derivation())
    pack_calls = _install_pack_ok(monkeypatch, tmp_path)

    ground.ground_from_repo(tmp_path)

    assert bridge_calls["run"] == 1  # exactly ONE derivation call (not per-trial)
    assert pack_calls["pack"] == 1


def test_ground_from_repo_missing_repomix_fails_loud(tmp_path: Path, monkeypatch):
    """Absent repomix raises RuntimeError with the install hint (no silent continue)."""
    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, _derivation())
    # repomix absent; run_pack must never be reached.
    monkeypatch.setattr(ground, "_find_repomix", lambda: "")
    monkeypatch.setattr(
        ground,
        "run_pack",
        lambda *a, **k: pytest.fail("run_pack must not run when repomix is absent"),
    )

    with pytest.raises(RuntimeError, match="repomix CLI not found"):
        ground.ground_from_repo(tmp_path)


def test_ground_from_repo_unparseable_json_fails_loud(tmp_path: Path, monkeypatch):
    """Malformed derivation JSON raises RuntimeError (fail loud, no garbage state)."""
    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, BridgeResult(success=True, output="not json", exit_code=0))
    _install_pack_ok(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="unparseable JSON"):
        ground.ground_from_repo(tmp_path)


def test_ground_from_repo_bridge_failure_fails_loud(tmp_path: Path, monkeypatch):
    """A failed derivation bridge call raises RuntimeError."""
    _write_readme(tmp_path)
    _install_stub_bridge(
        monkeypatch, BridgeResult(success=False, output="", exit_code=1, error="claude down")
    )
    _install_pack_ok(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="derivation call failed"):
        ground.ground_from_repo(tmp_path)


def test_main_returns_zero_on_success(tmp_path: Path, monkeypatch):
    """python -m bench.ground --root <repo> returns 0 on success."""
    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, _derivation())
    _install_pack_ok(monkeypatch, tmp_path)

    assert ground.main(["--root", str(tmp_path)]) == 0


def test_main_returns_nonzero_on_failure(tmp_path: Path, monkeypatch):
    """A grounding failure surfaces as a non-zero exit with a clear message."""
    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, _derivation())
    monkeypatch.setattr(ground, "_find_repomix", lambda: "")

    assert ground.main(["--root", str(tmp_path)]) == 1


def test_scaffold_synthetic_false_preserves_grounding(tmp_path: Path, monkeypatch):
    """scaffold(synthetic=False) preserves the grounded interview + pack, wipes memory.db.

    This is the preservation contract the verdict setup relies on: grounding is frozen
    on --root once, and every per-trial worktree copy inherits it via scaffold — the
    ONLY mutation is deleting memory.db so each trial starts from a clean compounding
    baseline.
    """
    from bench.project import scaffold

    _write_readme(tmp_path)
    _install_stub_bridge(monkeypatch, _derivation())
    _install_pack_ok(monkeypatch, tmp_path)
    ground.ground_from_repo(tmp_path)

    # Simulate the frozen pack + a stale memory.db that scaffold must wipe.
    pack = tmp_path / ".planning" / "codebase" / "repomix-pack.xml"
    pack.parent.mkdir(parents=True, exist_ok=True)
    pack.write_text("<pack/>")
    (tmp_path / "memory.db").write_text("stale run history")

    scaffold(tmp_path, synthetic=False)

    # Interview survives.
    state = load_state(tmp_path)
    assert state.interview.research_focus == "vector retrieval, channel adapters, prompt caching"
    # Pack survives.
    assert pack.is_file()
    # memory.db is wiped so the compounding baseline starts fresh.
    assert not (tmp_path / "memory.db").exists()
