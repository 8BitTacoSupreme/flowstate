"""Tests for discipline module — pure Python project audit."""

from pathlib import Path

from flowstate.discipline import check_setup


class TestCheckSetup:
    # These probe path-based checks only (identical on live/dry-run paths), so
    # they run under dry_run=True to stay side-effect-free (no pytest/git spawn).
    def test_empty_dir(self, tmp_path: Path):
        result = check_setup(tmp_path, dry_run=True)
        assert not result.success
        assert not result.checks["git_repo"]
        assert not result.checks["tests_dir"]
        assert "Audit:" in result.summary

    def test_with_git_repo(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        result = check_setup(tmp_path, dry_run=True)
        assert result.checks["git_repo"]

    def test_with_tests_dir(self, tmp_path: Path):
        (tmp_path / "tests").mkdir()
        result = check_setup(tmp_path, dry_run=True)
        assert result.checks["tests_dir"]

    def test_with_pyproject(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        result = check_setup(tmp_path, dry_run=True)
        assert result.checks["pytest_config"]

    def test_with_planning_dir(self, tmp_path: Path):
        (tmp_path / ".planning").mkdir()
        result = check_setup(tmp_path, dry_run=True)
        assert result.checks["planning_dir"]

    def test_with_python_package(self, tmp_path: Path):
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        result = check_setup(tmp_path, dry_run=True)
        assert result.checks["src_dir"]

    def test_full_project(self, tmp_path: Path):
        # A fully-provisioned repo passes on the dry-run path (tests reported-only).
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        hook = tmp_path / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)
        (tmp_path / "tests").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        (tmp_path / ".pre-commit-config.yaml").write_text("repos: []")
        (tmp_path / ".planning").mkdir()
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        result = check_setup(tmp_path, dry_run=True)
        assert result.success
        # tests_pass is reported-only (non-gating) on the dry-run path.
        assert all(v for k, v in result.checks.items() if k != "tests_pass")

    def test_summary_format(self, tmp_path: Path):
        result = check_setup(tmp_path, dry_run=True)
        assert "Audit:" in result.summary
        assert "[+]" in result.summary or "[-]" in result.summary

    def test_required_set_git_only_fails(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        result = check_setup(tmp_path, dry_run=True)
        assert not result.success

    def test_required_set_both_present_succeeds(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        result = check_setup(tmp_path, dry_run=True)
        assert result.success
        assert not result.checks["tests_dir"]
        assert not result.checks["pre_commit_config"]
