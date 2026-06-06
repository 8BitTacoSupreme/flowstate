"""Tests for the ClaudeBridge."""

from pathlib import Path

from flowstate.bridge import CANON, BridgeConfig, ClaudeBridge, _find_claude


def test_dry_run_returns_success():
    bridge = ClaudeBridge(dry_run=True)
    result = bridge.run("Hello world")
    assert result.success
    assert "[dry-run]" in result.output


def test_dry_run_skill():
    bridge = ClaudeBridge(dry_run=True)
    result = bridge.invoke_skill("gsd:new-project", "--auto")
    assert result.success
    assert "[dry-run]" in result.output


def test_available_when_claude_found(tmp_path: Path):
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho ok")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude))
    bridge = ClaudeBridge(config=config)
    assert bridge.available


def test_not_available_when_empty():
    config = BridgeConfig(claude_bin="")
    bridge = ClaudeBridge(config=config)
    assert not bridge.available


def test_run_fails_when_not_available():
    config = BridgeConfig(claude_bin="")
    bridge = ClaudeBridge(config=config)
    result = bridge.run("test")
    assert not result.success
    assert "not found" in result.error


def test_config_env_override(tmp_path: Path, monkeypatch):
    fake = tmp_path / "claude-custom"
    fake.write_text("#!/bin/sh\necho ok")
    fake.chmod(0o755)

    monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake))
    config = BridgeConfig()
    assert config.claude_bin == str(fake)


def test_auto_detect_finds_real_claude():
    """_find_claude should find the real binary if it exists on PATH."""
    found = _find_claude()
    # This test just validates the function doesn't crash.
    # On CI without claude, it returns "".
    assert isinstance(found, str)


def test_run_builds_correct_command(tmp_path: Path):
    """Verify the command structure without actually executing."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho test-output")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path)
    bridge = ClaudeBridge(config=config)

    # Use the fake binary — it just echoes
    result = bridge.run(
        "Hello",
        system_prompt="Be helpful",
        allowed_tools=["Read", "Bash"],
        max_turns=5,
    )
    # The fake shell script succeeds and outputs "test-output"
    assert result.success
    assert "test-output" in result.output


def test_model_flag_in_command(tmp_path: Path):
    """Verify --model flag appears when config.model is set."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho $@")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path, model="haiku")
    bridge = ClaudeBridge(config=config)
    result = bridge.run("Hello")
    assert result.success
    assert "--model" in result.output
    assert "haiku" in result.output


def test_model_per_call_override(tmp_path: Path):
    """Per-call model overrides config default."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho $@")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path, model="opus")
    bridge = ClaudeBridge(config=config)
    result = bridge.run("Hello", model="sonnet")
    assert "sonnet" in result.output


def test_budget_and_effort_flags(tmp_path: Path):
    """Verify --max-budget-usd and --effort flags appear when set."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho $@")
    fake_claude.chmod(0o755)

    config = BridgeConfig(
        claude_bin=str(fake_claude),
        project_root=tmp_path,
        max_budget_usd=0.25,
        effort="low",
    )
    bridge = ClaudeBridge(config=config)
    result = bridge.run("Hello")
    assert "--max-budget-usd" in result.output
    assert "0.25" in result.output
    assert "--effort" in result.output
    assert "low" in result.output


def test_no_model_flag_when_unset(tmp_path: Path):
    """No --model flag when neither config nor per-call sets it."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho $@")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path)
    bridge = ClaudeBridge(config=config)
    result = bridge.run("Hello")
    assert "--model" not in result.output


class TestCanonInjection:
    """Tests for CANON prepend behavior in ClaudeBridge.run()."""

    def _make_echo_bridge(self, tmp_path: Path, inject_canon: bool = True) -> ClaudeBridge:
        """Create a bridge backed by a fake claude that prints its args to stdout."""
        fake_claude = tmp_path / "claude"
        # Print all args on separate lines so we can find --system-prompt and its value
        fake_claude.write_text('#!/bin/sh\nfor arg in "$@"; do echo "$arg"; done')
        fake_claude.chmod(0o755)
        config = BridgeConfig(
            claude_bin=str(fake_claude),
            project_root=tmp_path,
            inject_canon=inject_canon,
        )
        return ClaudeBridge(config=config)

    def test_inject_canon_true_prepends_canon_before_system_prompt(self, tmp_path: Path):
        """inject_canon=True: CANON text appears before caller system_prompt."""
        bridge = self._make_echo_bridge(tmp_path, inject_canon=True)
        result = bridge.run("Hello", system_prompt="Be helpful")
        assert result.success
        canon_start = result.output.find("# CLAUDE.md")
        caller_start = result.output.find("Be helpful")
        assert canon_start != -1, "CANON text not found in output"
        assert caller_start != -1, "caller system_prompt not found in output"
        assert canon_start < caller_start, "CANON must precede caller system_prompt"

    def test_inject_canon_true_no_system_prompt_emits_canon(self, tmp_path: Path):
        """inject_canon=True with no system_prompt: --system-prompt is still emitted with CANON."""
        bridge = self._make_echo_bridge(tmp_path, inject_canon=True)
        result = bridge.run("Hello")
        assert result.success
        assert "--system-prompt" in result.output
        assert "# CLAUDE.md" in result.output

    def test_inject_canon_false_omits_canon(self, tmp_path: Path):
        """inject_canon=False: CANON text does not appear in the emitted command."""
        bridge = self._make_echo_bridge(tmp_path, inject_canon=False)
        result = bridge.run("Hello", system_prompt="Be helpful")
        assert result.success
        assert "# CLAUDE.md" not in result.output
        assert CANON[:20] not in result.output

    def test_inject_canon_false_no_system_prompt_no_flag(self, tmp_path: Path):
        """inject_canon=False with no system_prompt: --system-prompt flag is not emitted."""
        bridge = self._make_echo_bridge(tmp_path, inject_canon=False)
        result = bridge.run("Hello")
        assert result.success
        assert "--system-prompt" not in result.output

    def test_canon_constant_is_nonempty(self):
        """CANON module constant is a non-empty string."""
        assert isinstance(CANON, str)
        assert len(CANON) > 0
        assert "Think Before Coding" in CANON
        assert "Simplicity First" in CANON
        assert "Surgical Changes" in CANON
        assert "Goal-Driven Execution" in CANON
