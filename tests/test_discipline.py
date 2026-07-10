"""Tests for discipline module — pure Python project audit."""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from flowstate import discipline
from flowstate.discipline import (
    _check_hook_contents,
    _read_git_state,
    _run_project_tests,
    check_setup,
)

# Genuine subprocess.run, captured before any monkeypatch so routers can
# delegate real git calls while stubbing the pytest invocation.
_REAL_RUN = subprocess.run

_git_missing = shutil.which("git") is None


def _init_repo(path: Path) -> None:
    """Create a real git repo with one commit (offline, deterministic)."""
    _REAL_RUN(["git", "init"], cwd=path, check=True, capture_output=True)
    _REAL_RUN(
        ["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True
    )
    _REAL_RUN(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "seed.txt").write_text("x\n")
    _REAL_RUN(["git", "add", "."], cwd=path, check=True, capture_output=True)
    _REAL_RUN(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _pytest_router(returncode: int):
    """Route pytest invocations to a canned result; delegate everything else to real run."""

    def router(cmd, *args, **kwargs):
        if "pytest" in cmd:
            return subprocess.CompletedProcess(cmd, returncode, "", "")
        return _REAL_RUN(cmd, *args, **kwargs)

    return router


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


@pytest.mark.skipif(_git_missing, reason="git binary not available")
class TestReadGitState:
    def test_clean_repo_reports_branch_and_clean(self, tmp_path: Path):
        _init_repo(tmp_path)
        state = _read_git_state(tmp_path)
        assert isinstance(state["branch"], str) and state["branch"]
        assert state["dirty"] is False
        # No upstream configured -> ahead/behind stay None (None-tolerant, no crash).
        assert state["ahead"] is None
        assert state["behind"] is None

    def test_dirty_after_uncommitted_change(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "seed.txt").write_text("changed\n")
        state = _read_git_state(tmp_path)
        assert state["dirty"] is True

    def test_untracked_file_is_dirty(self, tmp_path: Path):
        _init_repo(tmp_path)
        (tmp_path / "new.txt").write_text("y\n")
        state = _read_git_state(tmp_path)
        assert state["dirty"] is True

    def test_non_repo_degrades_to_none(self, tmp_path: Path):
        # No .git — every git command fails; safe defaults, never raises.
        state = _read_git_state(tmp_path)
        assert state == {"branch": None, "dirty": None, "ahead": None, "behind": None}


class TestRunProjectTests:
    def test_returncode_zero_is_true(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(discipline.subprocess, "run", _pytest_router(0))
        assert _run_project_tests(tmp_path) is True

    def test_nonzero_is_false(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(discipline.subprocess, "run", _pytest_router(1))
        assert _run_project_tests(tmp_path) is False

    def test_exit_five_no_tests_is_false(self, tmp_path: Path, monkeypatch):
        # pytest exit 5 == "no tests collected" -> a real, gating failure.
        monkeypatch.setattr(discipline.subprocess, "run", _pytest_router(5))
        assert _run_project_tests(tmp_path) is False

    def test_missing_runner_is_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            discipline.subprocess,
            "run",
            Mock(side_effect=FileNotFoundError("no python")),
        )
        assert _run_project_tests(tmp_path) is None

    def test_timeout_is_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            discipline.subprocess,
            "run",
            Mock(side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=1)),
        )
        assert _run_project_tests(tmp_path) is None


@pytest.mark.skipif(_git_missing, reason="git binary not available")
class TestLiveGating:
    def _provision(self, tmp_path: Path) -> None:
        _init_repo(tmp_path)
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")

    def test_passing_suite_gates_success(self, tmp_path: Path, monkeypatch):
        self._provision(tmp_path)
        monkeypatch.setattr(discipline.subprocess, "run", _pytest_router(0))
        result = check_setup(tmp_path)
        assert result.success is True
        assert result.checks["tests_pass"] is True
        assert result.required == ("git_repo", "pytest_config", "tests_pass")
        assert "branch" in result.summary
        assert "Tests: passed" in result.summary

    def test_failing_suite_fails_audit(self, tmp_path: Path, monkeypatch):
        self._provision(tmp_path)
        monkeypatch.setattr(discipline.subprocess, "run", _pytest_router(1))
        result = check_setup(tmp_path)
        assert result.success is False
        assert result.checks["tests_pass"] is False
        assert "Tests: failed" in result.summary

    def test_absent_suite_fails_audit(self, tmp_path: Path, monkeypatch):
        # Runner cannot be invoked -> tests_pass None -> audit fails (not a fake pass).
        self._provision(tmp_path)

        def router(cmd, *args, **kwargs):
            if "pytest" in cmd:
                raise FileNotFoundError("no python")
            return _REAL_RUN(cmd, *args, **kwargs)

        monkeypatch.setattr(discipline.subprocess, "run", router)
        result = check_setup(tmp_path)
        assert result.success is False
        assert result.checks["tests_pass"] is False
        assert "Tests: not run" in result.summary


class TestDryRunZeroSpawn:
    def test_dry_run_spawns_no_subprocess(self, tmp_path: Path, monkeypatch):
        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        mock = Mock(side_effect=AssertionError("no subprocess in dry-run"))
        monkeypatch.setattr(discipline.subprocess, "run", mock)

        result = check_setup(tmp_path, dry_run=True)

        assert mock.call_count == 0
        assert result.success is True
        assert result.required == ("git_repo", "pytest_config")
        assert "Tests: skipped (dry-run)" in result.summary
        assert "Git state: skipped (dry-run)" in result.summary


class TestCheckHookContents:
    def _hook(self, tmp_path: Path) -> Path:
        hooks = tmp_path / ".git" / "hooks"
        hooks.mkdir(parents=True)
        return hooks / "pre-commit"

    def test_executable_nonempty_is_true(self, tmp_path: Path):
        hook = self._hook(tmp_path)
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o755)
        assert _check_hook_contents(tmp_path) is True

    def test_empty_is_false(self, tmp_path: Path):
        hook = self._hook(tmp_path)
        hook.write_text("")
        hook.chmod(0o755)
        assert _check_hook_contents(tmp_path) is False

    def test_non_executable_is_false(self, tmp_path: Path):
        hook = self._hook(tmp_path)
        hook.write_text("#!/bin/sh\nexit 0\n")
        hook.chmod(0o644)
        assert _check_hook_contents(tmp_path) is False

    def test_absent_is_false(self, tmp_path: Path):
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        assert _check_hook_contents(tmp_path) is False
