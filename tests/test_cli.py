"""Tests for the FlowState CLI."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from flowstate.cli import main


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
