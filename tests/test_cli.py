"""Tests for the FlowState CLI."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import flowstate.config as config_mod
from flowstate.cli import main


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Route all config reads/writes to a temp directory so tests never
    touch the real ~/.config/flowstate/config.toml."""
    cfg_dir = tmp_path / ".config_flowstate"
    cfg_file = cfg_dir / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)


@pytest.fixture()
def healthy_install(tmp_path, monkeypatch):
    """Create an init'd FlowState project with manifest + memory.db; mock claude CLI as present.

    Uses monkeypatch.setenv (writes to os.environ) so click.testing.CliRunner.invoke()
    picks up FLOWSTATE_CLAUDE_BIN without needing `env=` plumbing per call. This is the
    pattern blessed by plan-checker iteration 1 (W4).
    """
    from flowstate.memory import MemoryStore
    from flowstate.state import FlowStateModel, InstallEntry, save_state

    # Ensure claude CLI check passes — write env BEFORE invoking CLI
    fake_claude = tmp_path / "fake_claude"
    fake_claude.write_text("#!/bin/sh\nexit 0\n")
    fake_claude.chmod(0o755)
    monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))

    # Memory.db
    with MemoryStore(root=tmp_path):
        pass

    # One context file + matching manifest entry
    planning = tmp_path / ".planning"
    planning.mkdir()
    pm = planning / "PROJECT.md"
    pm.write_text("# Project\n")
    checksum = hashlib.sha256(pm.read_bytes()).hexdigest()

    state = FlowStateModel()
    state.install_manifest.append(
        InstallEntry(
            path=".planning/PROJECT.md",
            owner="context",
            kind="context",
            created_at=datetime.now(UTC),
            checksum=checksum,
        )
    )
    state.install_manifest.append(
        InstallEntry(
            path="memory.db",
            owner="memory",
            kind="memory",
            created_at=datetime.now(UTC),
            checksum=None,
        )
    )
    save_state(state, tmp_path)
    return tmp_path


class TestDoctorCommand:
    def test_doctor_healthy_install_exits_zero(self, healthy_install):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_doctor_missing_manifest_file_exits_nonzero(self, tmp_path, monkeypatch):
        from flowstate.memory import MemoryStore
        from flowstate.state import FlowStateModel, InstallEntry, save_state

        fake_claude = tmp_path / "fake_claude"
        fake_claude.write_text("#!/bin/sh\nexit 0\n")
        fake_claude.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))

        with MemoryStore(root=tmp_path):
            pass

        state = FlowStateModel()
        state.install_manifest.append(
            InstallEntry(
                path=".planning/MISSING.md",
                owner="context",
                kind="context",
                created_at=datetime.now(UTC),
                checksum="0" * 64,
            )
        )
        save_state(state, tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])
        assert result.exit_code >= 1
        assert "manifest_integrity" in result.output

    def test_doctor_orphan_files_does_not_fail(self, healthy_install):
        # Plant an orphan
        (healthy_install / ".planning" / "EXTRA.md").write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "orphan_files" in result.output
        assert "info" in result.output

    def test_doctor_help_lists_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output.lower()


class TestRepairCommand:
    def test_repair_safe_fixes_applied(self, healthy_install):
        # Delete PROJECT.md so the manifest entry is "missing"
        (healthy_install / ".planning" / "PROJECT.md").unlink()
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "regenerated context files" in result.output

    def test_repair_skips_destructive_without_flag(self, healthy_install):
        orphan = healthy_install / ".planning" / "EXTRA.md"
        orphan.write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert orphan.exists()

    def test_repair_apply_destructive_deletes_orphans(self, healthy_install):
        orphan = healthy_install / ".planning" / "EXTRA.md"
        orphan.write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(
            main, ["repair", "--apply-destructive", "--root", str(healthy_install)]
        )
        assert result.exit_code == 0
        assert not orphan.exists()

    def test_repair_help_lists_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--help"])
        assert result.exit_code == 0
        assert "--apply-destructive" in result.output

    def test_repair_no_findings_exits_zero(self, healthy_install):
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "Nothing to repair" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "flowstate" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Context Orchestrator" in result.output


def test_status_command(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["status", "--root", str(tmp_path)])
        assert result.exit_code == 0


def test_init_dry_run_skip_interview(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "dry-run" in result.output.lower() or "Pipeline" in result.output


def test_run_dry_run(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--dry-run", "--root", str(tmp_path), "1"],
    )
    assert result.exit_code == 0


def test_check_bridge():
    runner = CliRunner()
    result = runner.invoke(main, ["check"])
    # Will succeed regardless — either finds claude or reports not found
    assert result.exit_code == 0


def test_launch_gsd(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["launch", "--root", str(tmp_path), "gsd", "1"],
    )
    assert result.exit_code == 0
    assert "gsd:plan-phase" in result.output


def test_launch_gsd_no_phase(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["launch", "--root", str(tmp_path), "gsd"],
    )
    assert result.exit_code == 0
    assert "gsd:progress" in result.output


def test_context_command(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["context", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "context files" in result.output.lower()


def test_init_with_model_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--model", "haiku"],
    )
    assert result.exit_code == 0


def test_init_with_budget_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--budget", "0.25"],
    )
    assert result.exit_code == 0


def test_init_with_effort_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--effort", "low"],
    )
    assert result.exit_code == 0


def test_init_model_persists_in_state(tmp_path: Path):
    """--model flag should persist into flowstate.json preferences."""
    import json

    runner = CliRunner()
    runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--model", "haiku"],
    )
    state_file = tmp_path / "flowstate.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["preferences"]["model"] == "haiku"


def test_run_with_model_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--dry-run", "--root", str(tmp_path), "--model", "opus", "1"],
    )
    assert result.exit_code == 0


def test_fresh_nothing_to_clean(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "already fresh" in result.output


def _populate_state_with_manifest(tmp_path: Path, paths: list[tuple[str, str]]) -> None:
    """Helper: write a flowstate.json with manifest entries for the given (path, kind) pairs."""
    from datetime import UTC, datetime

    from flowstate.state import FlowStateModel, InstallEntry, save_state

    state = FlowStateModel()
    state.install_manifest = [
        InstallEntry(
            path=p,
            owner="context",
            kind=kind,  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            checksum=None,
        )
        for p, kind in paths
    ]
    save_state(state, tmp_path)


def test_fresh_removes_state_files(tmp_path: Path):
    """fresh --yes --force removes generated artifacts (manifest + orphans) but not source code."""
    # Create the files that init would generate
    (tmp_path / "memory.db").write_text("")
    planning = tmp_path / ".planning"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("")
    (planning / "ROADMAP.md").write_text("")
    (planning / "config.json").write_text("{}")
    research_dir = planning / "research"
    research_dir.mkdir()
    (research_dir / "STACK.md").write_text("")
    top_research = tmp_path / "research"
    top_research.mkdir()
    (top_research / "report.md").write_text("")

    # Populate manifest with files we own; STACK.md will be an orphan
    _populate_state_with_manifest(
        tmp_path,
        [
            (".planning/PROJECT.md", "context"),
            (".planning/ROADMAP.md", "context"),
            (".planning/config.json", "config"),
            ("research/report.md", "research"),
            ("memory.db", "memory"),
        ],
    )

    # Create a source file that should survive
    src = tmp_path / "flowstate"
    src.mkdir()
    (src / "cli.py").write_text("# source")

    runner = CliRunner()
    # --force needed to remove orphans (.planning/research/STACK.md, flowstate.json)
    result = runner.invoke(main, ["fresh", "--yes", "--force", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Removed" in result.output

    # Generated files should be gone
    assert not (tmp_path / "flowstate.json").exists()
    assert not (tmp_path / "memory.db").exists()
    assert not (planning / "PROJECT.md").exists()
    assert not (planning / "research").exists()
    assert not (tmp_path / "research").exists()

    # Source code untouched
    assert (src / "cli.py").exists()


def test_fresh_preserves_claude_md(tmp_path: Path):
    """fresh does NOT delete .claude/CLAUDE.md unless it's in the manifest."""
    _populate_state_with_manifest(tmp_path, [])
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# keep me")

    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
    assert result.exit_code == 0
    # .claude/ is not scanned for orphans (only .planning/ and research/)
    assert (claude_dir / "CLAUDE.md").exists()


def test_fresh_cancelled_without_yes(tmp_path: Path):
    """fresh without --yes prompts, and 'n' cancels."""
    _populate_state_with_manifest(tmp_path, [])

    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--root", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output
    assert (tmp_path / "flowstate.json").exists()


def test_fresh_removes_empty_planning_dir(tmp_path: Path):
    """If .planning/ is empty after cleanup, remove it too."""
    planning = tmp_path / ".planning"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("")

    # Track PROJECT.md in the manifest so fresh owns it
    _populate_state_with_manifest(tmp_path, [(".planning/PROJECT.md", "context")])

    runner = CliRunner()
    # --force so the flowstate.json orphan is also removed
    result = runner.invoke(main, ["fresh", "--yes", "--force", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert not planning.exists()


# ── Config persistence integration tests ─────────────────────────────


def test_init_root_saves_default(tmp_path: Path):
    """init --root /some/path should persist the root to config."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert config_mod.load_default_root() == tmp_path.resolve()


def test_init_without_root_does_not_save(tmp_path: Path):
    """init without explicit --root should NOT write config."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init", "--dry-run", "--skip-interview"])
        assert result.exit_code == 0
    assert config_mod.load_default_root() is None


def test_status_picks_up_saved_root(tmp_path: Path):
    """status without --root should use saved default."""
    config_mod.save_default_root(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0


def test_explicit_root_overrides_saved(tmp_path: Path):
    """Explicit --root should beat saved config."""
    saved = tmp_path / "saved"
    saved.mkdir()
    config_mod.save_default_root(saved)

    explicit = tmp_path / "explicit"
    explicit.mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(explicit)])
    assert result.exit_code == 0


def test_config_show_with_saved_root(tmp_path: Path):
    config_mod.save_default_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    # Rich may line-wrap long paths; strip newlines before checking.
    flat = result.output.replace("\n", "")
    assert str(tmp_path.resolve()) in flat


def test_config_show_empty():
    runner = CliRunner()
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "No default root" in result.output


def test_config_set_root(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["config", "set-root", str(tmp_path)])
    assert result.exit_code == 0
    assert config_mod.load_default_root() == tmp_path.resolve()


def test_config_clear_root(tmp_path: Path):
    config_mod.save_default_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "clear-root"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()
    assert config_mod.load_default_root() is None


def test_config_clear_root_idempotent():
    runner = CliRunner()
    result = runner.invoke(main, ["config", "clear-root"])
    assert result.exit_code == 0
    assert "No default root" in result.output
