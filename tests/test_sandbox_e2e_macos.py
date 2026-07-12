"""E2E tests for the macOS `confine` sandbox tier — real sandbox-exec, no mocking.

Task 1 (SBX-05): proves the shipped `build_macos_profile` allow-default +
selective-deny profile, exercised through the real `wrap(..., tier="confine")`
dispatch and a real `subprocess.run()` invocation of `sandbox-exec`, allows a
write inside `project_root` while denying a write outside it (under `$HOME`)
and denying a read of `~/.ssh`.

Skip-gated on darwin — mirrors `tests/test_discipline.py`'s binary-presence
`skipif` idiom, translated to a platform-presence gate — so this file is
CI-runnable on macOS runners and skips cleanly everywhere else.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from flowstate.sandbox import wrap

# Genuine subprocess.run, captured before any monkeypatch (none in this file) —
# mirrors the house pattern in tests/test_discipline.py.
_REAL_RUN = subprocess.run

_not_darwin = sys.platform != "darwin"


def _run_confined(script: str, project_root: Path) -> subprocess.CompletedProcess:
    """Real wrap(tier="confine") + real subprocess.run of a /bin/sh -c script.

    Unlinks the temp `.sb` profile written by `_wrap_macos` in a `finally` —
    this test drives `wrap()` directly (not through the bridge's WR-09
    cleanup), so it owns its own cleanup.
    """
    cmd, env = wrap(
        ["/bin/sh", "-c", script], "llm", project_root, os.environ.copy(), tier="confine"
    )
    profile_path = cmd[2]  # [sandbox-exec, "-f", <profile>, *cmd] shape (_wrap_macos)
    try:
        return _REAL_RUN(cmd, capture_output=True, text=True, timeout=10, env=env)
    finally:
        Path(profile_path).unlink(missing_ok=True)


@pytest.mark.skipif(_not_darwin, reason="macOS sandbox-exec only")
class TestMacosConfineDenialE2E:
    """Task 1: real sandbox-exec proves allow-inside / deny-outside / deny-~/.ssh."""

    def test_write_inside_project_root_succeeds(self, tmp_path: Path):
        target = tmp_path / "inside.txt"

        result = _run_confined(f'echo hello > "{target}"', tmp_path)

        assert result.returncode == 0, result.stderr
        assert target.exists()
        assert target.read_text() == "hello\n"

    def test_write_outside_project_root_denied(self, tmp_path: Path):
        # Outside project_root AND outside the profile's re-allowed
        # /private/tmp, /private/var/folders, /dev subpaths.
        escape_target = Path.home() / "flowstate_sbx_escape_test.txt"
        escape_target.unlink(missing_ok=True)
        try:
            result = _run_confined(f'echo escaped > "{escape_target}"', tmp_path)

            assert result.returncode != 0
            assert not escape_target.exists(), "confined write escaped project_root"
        finally:
            escape_target.unlink(missing_ok=True)

    def test_read_of_ssh_denied(self, tmp_path: Path):
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.is_dir():
            pytest.skip("no ~/.ssh directory on this host to probe")

        result = _run_confined(f'ls -la "{ssh_dir}"', tmp_path)

        assert result.returncode != 0
        # Directory read denied outright — no listing/content leaked to stdout.
        assert result.stdout.strip() == ""
