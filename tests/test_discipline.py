"""Tests for discipline module — pure Python project audit."""

from pathlib import Path

from flowstate.discipline import check_setup, check_superpowers_installed


class TestCheckSetup:
    def test_empty_dir(self, tmp_path: Path):
        result = check_setup(tmp_path)
        assert result.success
        assert not result.checks["git_repo"]
        assert not result.checks["tests_dir"]
        assert "Audit:" in result.summary

    def test_with_git_repo(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        result = check_setup(tmp_path)
        assert result.checks["git_repo"]

    def test_with_tests_dir(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        result = check_setup(tmp_path)
        assert result.checks["tests_dir"]

    def test_with_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        result = check_setup(tmp_path)
        assert result.checks["pytest_config"]

    def test_with_planning_dir(self, tmp_path: Path):
        (tmp_path / ".planning").mkdir()
        result = check_setup(tmp_path)
        assert result.checks["planning_dir"]

    def test_with_python_package(self, tmp_path: Path):
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        result = check_setup(tmp_path)
        assert result.checks["src_dir"]

    def test_full_project(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        (tmp_path / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh")
        (tmp_path / "tests").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        (tmp_path / ".planning").mkdir()
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        result = check_setup(tmp_path)
        assert result.success
        assert all(result.checks.values())

    def test_summary_format(self, tmp_path: Path):
        result = check_setup(tmp_path)
        assert "Audit:" in result.summary
        assert "[+]" in result.summary or "[-]" in result.summary


def test_check_superpowers_installed():
    # Just verify it doesn't crash — result depends on the machine
    result = check_superpowers_installed()
    assert isinstance(result, bool)
