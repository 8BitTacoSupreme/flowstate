"""Offline tests for the GSD install path added to flowstate.installer.

`install_skills` lays down the FULL vendored GSD distribution UNCONDITIONALLY:
- GSD skills into ``.claude/skills/gsd-*``
- the ``get-shit-done`` runtime into ``.claude/get-shit-done/``
- the ``gsd-sdk`` CLI + the ``node_modules`` it needs to resolve, so
  ``node <installed>/gsd-sdk.js`` runs with full parity.

All tests run offline against a temp project dir — no network, no ``claude`` CLI.
The 51M vendored tree is installed once per module via a shared fixture for the
read-only layout assertions; mutating tests use their own temp project.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from flowstate.installer import install_gsd, install_skills
from flowstate.state import FlowStateModel

# Installed layout landmarks (relative to project root).
RUNTIME_WORKFLOWS = ".claude/get-shit-done/workflows"
GSD_SDK = ".claude/get-shit-done/node_modules/get-shit-done-cc/bin/gsd-sdk.js"
GSD_SDK_DEP = ".claude/get-shit-done/node_modules/@anthropic-ai/claude-agent-sdk"
A_GSD_SKILL = ".claude/skills/gsd-plan-phase/SKILL.md"


@pytest.fixture(scope="module")
def installed_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Install the real vendored GSD once; reused by read-only layout tests."""
    root = tmp_path_factory.mktemp("gsd_project")
    install_skills(root)
    return root


def test_gsd_runtime_and_skills_land(installed_project: Path):
    assert (installed_project / RUNTIME_WORKFLOWS).is_dir()
    assert (installed_project / A_GSD_SKILL).is_file()
    # Multiple gsd-* skill dirs are created (not a flat dump of *.md).
    skills = list((installed_project / ".claude/skills").glob("gsd-*"))
    assert len(skills) > 10
    assert all(p.is_dir() and (p / "SKILL.md").is_file() for p in skills)


def test_gsd_sdk_cli_present(installed_project: Path):
    assert (installed_project / GSD_SDK).is_file()


def test_gsd_sdk_node_modules_colocated(installed_project: Path):
    """gsd-sdk's runtime deps travel with it so `node <sdk>` resolves them."""
    assert (installed_project / GSD_SDK_DEP).is_dir()
    assert (installed_project / ".claude/get-shit-done/node_modules/ws").is_dir()


def test_gsd_skill_frontmatter_name_is_hyphenated(installed_project: Path):
    """Skills are renamed gsd-<cmd> (not the source `gsd:<cmd>`)."""
    content = (installed_project / A_GSD_SKILL).read_text()
    assert content.startswith("---")
    assert "name: gsd-plan-phase" in content
    assert "name: gsd:plan-phase" not in content


def test_gsd_install_is_unconditional_no_gate(tmp_path: Path):
    """No detect/prompt — an empty project still gets the full GSD tree."""
    assert not (tmp_path / ".claude").exists()
    install_skills(tmp_path)
    assert (tmp_path / RUNTIME_WORKFLOWS).is_dir()
    assert (tmp_path / GSD_SDK).is_file()


def test_gsd_dry_run_writes_nothing_but_returns_dests(tmp_path: Path):
    result = install_skills(tmp_path, dry_run=True)
    assert not (tmp_path / ".claude").exists()
    names = {p.name for p in result}
    # The GSD tree dests are surfaced even on a dry run.
    assert "get-shit-done" in names
    assert "node_modules" in names


def test_gsd_install_is_idempotent(tmp_path: Path):
    install_gsd(tmp_path)
    first = sorted(
        p.relative_to(tmp_path) for p in (tmp_path / ".claude/skills").rglob("*") if p.is_file()
    )
    install_gsd(tmp_path)  # second run must not raise or duplicate
    second = sorted(
        p.relative_to(tmp_path) for p in (tmp_path / ".claude/skills").rglob("*") if p.is_file()
    )
    assert first == second


def test_gsd_manifest_records_dests(tmp_path: Path):
    state = FlowStateModel()
    install_gsd(tmp_path, state=state)
    paths = {e.path for e in state.install_manifest}
    assert ".claude/get-shit-done" in paths
    assert ".claude/get-shit-done/node_modules" in paths
    assert ".claude/skills/gsd-plan-phase" in paths
    for e in state.install_manifest:
        assert e.kind == "artifact"
        assert e.owner == "gsd"


def test_gsd_manifest_idempotent_on_reinstall(tmp_path: Path):
    state = FlowStateModel()
    install_gsd(tmp_path, state=state)
    install_gsd(tmp_path, state=state)
    gsd_entries = [e for e in state.install_manifest if e.owner == "gsd"]
    assert len(gsd_entries) == len(set(e.path for e in gsd_entries))


def test_gsd_dry_run_does_not_touch_manifest(tmp_path: Path):
    state = FlowStateModel()
    install_gsd(tmp_path, dry_run=True, state=state)
    assert state.install_manifest == []


def test_gsd_path_traversal_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A crafted mapping cannot escape root/.claude."""
    import flowstate.installer as installer_mod

    monkeypatch.setattr(
        installer_mod,
        "_GSD_TREE_MAPPINGS",
        [("node_modules", "../../escape")],
    )
    with pytest.raises(ValueError, match=r"outside \.claude"):
        install_gsd(tmp_path)


def test_gsd_does_not_clobber_user_skills(tmp_path: Path):
    user = tmp_path / ".claude/skills/mine/custom.md"
    user.parent.mkdir(parents=True)
    user.write_text("mine")
    install_gsd(tmp_path)
    assert user.read_text() == "mine"
    assert (tmp_path / A_GSD_SKILL).is_file()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_gsd_sdk_full_parity_query(tmp_path: Path):
    """Confirmatory (node-gated): the installed gsd-sdk answers a real query.

    Authoritative parity proof is 15-01's recorded exit-0; this re-confirms it
    from the installed tree. Skipped only when `node` is absent.
    """
    install_skills(tmp_path)
    (tmp_path / ".planning").mkdir()
    (tmp_path / ".planning/ROADMAP.md").write_text(
        "# Roadmap\n\n## Phase 1: Bundle GSD\n\nSome content.\n"
    )
    sdk = tmp_path / GSD_SDK
    proc = subprocess.run(
        ["node", str(sdk), "query", "roadmap.get-phase", "1"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Bundle GSD" in proc.stdout


def test_gsd_install_copies_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The installer must never spawn a subprocess against vendored files."""

    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("install must not execute vendored code")

    # Trip any subprocess/os spawn attempt during install.
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr("os.system", _boom)
    install_gsd(tmp_path)
    assert (tmp_path / GSD_SDK).is_file()
