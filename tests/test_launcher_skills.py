"""Offline tests for skill-gated launch handoffs (VEND-04).

`flowstate launch strategy` → gstack `/office-hours`; `flowstate launch discipline`
→ superpowers `test-driven-development` — but only when the vendored skills are
installed in `.claude/skills/`. When absent, the launcher must direct the user to
`flowstate install-skills` rather than emit a broken/misleading handoff.
"""

from pathlib import Path

from flowstate.launcher import launch_command


def _install(root: Path, namespace: str) -> None:
    """Create the minimal installed-skill marker directory for `namespace`."""
    (root / ".claude" / "skills" / namespace).mkdir(parents=True, exist_ok=True)


class TestStrategyHandoff:
    def test_office_hours_when_gstack_installed(self, tmp_path: Path):
        _install(tmp_path, "gstack")
        cmd = launch_command("strategy", None, tmp_path)
        assert "/office-hours" in cmd
        assert "claude" in cmd

    def test_install_prompt_when_gstack_absent(self, tmp_path: Path):
        cmd = launch_command("strategy", None, tmp_path)
        assert "install-skills" in cmd
        assert "/office-hours" not in cmd


class TestDisciplineHandoff:
    def test_tdd_when_superpowers_installed(self, tmp_path: Path):
        _install(tmp_path, "superpowers")
        cmd = launch_command("discipline", None, tmp_path)
        assert "test-driven-development" in cmd
        assert "claude" in cmd

    def test_install_prompt_when_superpowers_absent(self, tmp_path: Path):
        cmd = launch_command("discipline", None, tmp_path)
        assert "install-skills" in cmd
        assert "test-driven-development" not in cmd

    def test_discipline_gate_is_independent_of_gstack(self, tmp_path: Path):
        # gstack installed but superpowers absent → discipline still gated off.
        _install(tmp_path, "gstack")
        cmd = launch_command("discipline", None, tmp_path)
        assert "install-skills" in cmd
        assert "test-driven-development" not in cmd
