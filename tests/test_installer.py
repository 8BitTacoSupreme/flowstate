"""Offline tests for flowstate.installer — the vendored-skills installer.

All tests run against a temp project dir; no network, no LLM, no real project state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowstate.installer import install_skills
from flowstate.state import FlowStateModel

GSTACK_MARKER = ".claude/skills/gstack/office-hours/SKILL.md"
SUPERPOWERS_MARKER = ".claude/skills/superpowers/test-driven-development/SKILL.md"


def test_install_creates_both_namespaces(tmp_path: Path):
    install_skills(tmp_path)
    assert (tmp_path / GSTACK_MARKER).exists()
    assert (tmp_path / SUPERPOWERS_MARKER).exists()


def test_install_returns_namespace_paths(tmp_path: Path):
    result = install_skills(tmp_path)
    names = {p.name for p in result}
    # gstack + superpowers land under .claude/skills; GSD adds its own dests too.
    assert {"gstack", "superpowers"} <= names
    for p in result:
        assert p == p.resolve()
        assert (tmp_path / ".claude") in p.parents


def test_install_is_idempotent(tmp_path: Path):
    install_skills(tmp_path)
    first = sorted(p for p in (tmp_path / ".claude/skills").rglob("*") if p.is_file())
    # Second install must not raise and must yield the same tree.
    install_skills(tmp_path)
    second = sorted(p for p in (tmp_path / ".claude/skills").rglob("*") if p.is_file())
    assert first == second


def test_install_does_not_clobber_user_skills(tmp_path: Path):
    user_file = tmp_path / ".claude/skills/mine/custom.md"
    user_file.parent.mkdir(parents=True)
    user_file.write_text("my own skill")

    install_skills(tmp_path)

    assert user_file.exists()
    assert user_file.read_text() == "my own skill"
    # And the vendored namespaces landed alongside it.
    assert (tmp_path / GSTACK_MARKER).exists()


def test_dry_run_writes_nothing(tmp_path: Path):
    result = install_skills(tmp_path, dry_run=True)
    assert not (tmp_path / ".claude").exists()
    # dry_run still reports what WOULD be written (skills + GSD dests).
    assert {"gstack", "superpowers"} <= {p.name for p in result}


def test_dry_run_does_not_touch_manifest(tmp_path: Path):
    state = FlowStateModel()
    install_skills(tmp_path, dry_run=True, state=state)
    assert state.install_manifest == []


def test_manifest_records_both_namespaces(tmp_path: Path):
    state = FlowStateModel()
    install_skills(tmp_path, state=state)

    paths = {e.path for e in state.install_manifest}
    assert ".claude/skills/gstack" in paths
    assert ".claude/skills/superpowers" in paths
    # Scope the owner/kind assertions to the vendored-skills namespaces; GSD
    # registers its own entries under owner="gsd".
    for e in (e for e in state.install_manifest if e.owner == "skills"):
        assert e.kind == "artifact"
        assert e.checksum is None


def test_manifest_idempotent_on_reinstall(tmp_path: Path):
    state = FlowStateModel()
    install_skills(tmp_path, state=state)
    install_skills(tmp_path, state=state)
    skill_entries = [e for e in state.install_manifest if e.owner == "skills"]
    # Exactly two entries (one per vendored-skills namespace) — no duplicates.
    assert len(skill_entries) == 2


def test_source_symlink_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A symlink in the source tree must never be followed out of the tree."""
    # Build a fake source skills tree with a symlink escaping it.
    fake_pkg = tmp_path / "pkg"
    src = fake_pkg / "skills"
    (src / "gstack" / "office-hours").mkdir(parents=True)
    (src / "gstack" / "office-hours" / "SKILL.md").write_text("gstack")
    (src / "superpowers" / "test-driven-development").mkdir(parents=True)
    (src / "superpowers" / "test-driven-development" / "SKILL.md").write_text("tdd")

    outside = tmp_path / "secret.txt"
    outside.write_text("SECRET")
    escape = src / "gstack" / "escape"
    escape.symlink_to(outside)

    import flowstate.installer as installer_mod

    monkeypatch.setattr(installer_mod, "_skills_source", lambda: src)

    dest_root = tmp_path / "proj"
    install_skills(dest_root)

    # The symlink must not have been materialized into the destination.
    assert not (dest_root / ".claude/skills/gstack/escape").exists()
    # But the real files copied fine.
    assert (dest_root / ".claude/skills/gstack/office-hours/SKILL.md").exists()


def test_destination_confined_to_claude_dir(tmp_path: Path):
    """install_skills only ever writes under root/.claude (skills + GSD runtime)."""
    install_skills(tmp_path)
    claude_root = (tmp_path / ".claude").resolve()
    for p in (tmp_path / ".claude").rglob("*"):
        resolved = p.resolve()
        assert claude_root == resolved or claude_root in resolved.parents
