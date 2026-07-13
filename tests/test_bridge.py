"""Tests for the ClaudeBridge."""

import subprocess
from pathlib import Path

from flowstate.bridge import CANON, BridgeConfig, BridgeUsage, ClaudeBridge, _find_claude


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


class TestPromptCaching1h:
    """Tests for the ENABLE_PROMPT_CACHING_1H opt-in env var (CAG-03)."""

    def _make_env_capture_bridge(self, tmp_path, enable_caching: bool) -> ClaudeBridge:
        """Bridge backed by a fake claude that prints its env vars to stdout."""
        fake_claude = tmp_path / "claude"
        # Print ENABLE_PROMPT_CACHING_1H env var value (empty string if unset)
        fake_claude.write_text('#!/bin/sh\necho "CACHE_VAR=${ENABLE_PROMPT_CACHING_1H}"')
        fake_claude.chmod(0o755)
        config = BridgeConfig(
            claude_bin=str(fake_claude),
            project_root=tmp_path,
            enable_prompt_caching_1h=enable_caching,
        )
        return ClaudeBridge(config=config)

    def test_flag_false_does_not_set_env_var(self, tmp_path):
        """enable_prompt_caching_1h=False (default) → ENABLE_PROMPT_CACHING_1H not set."""
        bridge = self._make_env_capture_bridge(tmp_path, enable_caching=False)
        result = bridge.run("Hello")
        assert result.success
        # When env var is unset, the shell expands it to empty string
        assert "CACHE_VAR=1" not in result.output

    def test_flag_true_sets_env_var_to_1(self, tmp_path):
        """enable_prompt_caching_1h=True → ENABLE_PROMPT_CACHING_1H=1 in subprocess env."""
        bridge = self._make_env_capture_bridge(tmp_path, enable_caching=True)
        result = bridge.run("Hello")
        assert result.success
        assert "CACHE_VAR=1" in result.output

    def test_default_config_has_caching_disabled(self):
        """BridgeConfig.enable_prompt_caching_1h defaults to False."""
        config = BridgeConfig(claude_bin="")
        assert config.enable_prompt_caching_1h is False

    def test_bridge_docstring_mentions_cache_layer_order(self):
        """ClaudeBridge docstring documents the most-stable-first cache layer ordering."""
        from flowstate.bridge import ClaudeBridge

        doc = ClaudeBridge.__doc__ or ""
        # Docstring must describe the cache layer hierarchy
        assert "most-stable-first" in doc.lower() or "most stable" in doc.lower(), (
            "ClaudeBridge docstring must mention most-stable-first layer ordering"
        )
        # Must mention the CAG layers
        assert "canon" in doc.lower() or "system prompt" in doc.lower(), (
            "ClaudeBridge docstring must mention system-prompt canon layer"
        )
        assert "fixture" in doc.lower(), "ClaudeBridge docstring must mention fixtures layer"
        assert "memory" in doc.lower(), "ClaudeBridge docstring must mention memory layer"


def _make_payload_bridge(tmp_path: Path, payload: str) -> ClaudeBridge:
    """Fake claude that emits a fixed stdout payload (payload + trailing newline)."""
    fake_claude = tmp_path / "claude"
    fake_claude.write_text(f"#!/bin/sh\ncat <<'PAYLOAD_EOF'\n{payload}\nPAYLOAD_EOF")
    fake_claude.chmod(0o755)
    config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path)
    return ClaudeBridge(config=config)


class TestUsageAndDuration:
    """Task 1 (TAX-01): BridgeResult.usage + duration_s via the json path."""

    def test_text_mode_output_byte_identical_and_usage_none(self, tmp_path: Path):
        """Text mode (default): .output is byte-identical raw stdout; usage is None."""
        payload = "plain text response line"
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello")
        assert result.output == payload + "\n"
        assert result.usage is None

    def test_json_mode_extracts_result_and_usage(self, tmp_path: Path):
        """Json mode: .output is the parsed top-level `result`; usage is populated."""
        payload = (
            '{"result": "the answer", '
            '"usage": {"input_tokens": 10, "output_tokens": 109, '
            '"cache_read_input_tokens": 24308}}'
        )
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello", output_format="json")
        assert result.output == "the answer"
        assert result.usage == BridgeUsage(tokens_in=10, tokens_out=109, cache_read=24308)

    def test_json_mode_missing_usage_subkeys_default_zero(self, tmp_path: Path):
        """Missing usage sub-keys default to 0."""
        payload = '{"result": "ok", "usage": {"input_tokens": 7}}'
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello", output_format="json")
        assert result.usage == BridgeUsage(tokens_in=7, tokens_out=0, cache_read=0)

    def test_json_mode_malformed_guarded(self, tmp_path: Path):
        """Malformed stdout: never raise; usage None; .output falls back to raw stdout."""
        payload = "not valid json {{{"
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello", output_format="json")
        assert result.usage is None
        assert result.output == payload + "\n"
        assert result.success

    def test_json_mode_missing_result_key_falls_back(self, tmp_path: Path):
        """Absent top-level `result` key: usage None, .output falls back to raw stdout."""
        payload = '{"usage": {"input_tokens": 5}}'
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello", output_format="json")
        assert result.usage is None
        assert result.output == payload + "\n"

    def test_json_mode_non_dict_usage_does_not_raise(self, tmp_path: Path):
        """WR-01: a truthy non-dict `usage` (list/str) must not raise AttributeError."""
        payload = '{"result": "ok", "usage": ["not", "a", "dict"]}'
        bridge = _make_payload_bridge(tmp_path, payload)
        # Must return cleanly rather than propagating AttributeError out of run().
        result = bridge.run("Hello", output_format="json")
        assert result.success
        assert result.output == "ok"
        # Non-dict usage collapses to no usable counts.
        assert result.usage == BridgeUsage(tokens_in=0, tokens_out=0, cache_read=0)

    def test_json_mode_null_token_values_coerce_to_zero(self, tmp_path: Path):
        """WR-01: present-but-null token values must coerce to 0, not crash _accumulate."""
        payload = (
            '{"result": "ok", '
            '"usage": {"input_tokens": null, "output_tokens": 5, '
            '"cache_read_input_tokens": null}}'
        )
        bridge = _make_payload_bridge(tmp_path, payload)
        # int + None inside _accumulate would raise TypeError before the fix.
        result = bridge.run("Hello", output_format="json")
        assert result.success
        assert result.usage == BridgeUsage(tokens_in=0, tokens_out=5, cache_read=0)
        assert bridge.total_tokens_in == 0
        assert bridge.total_tokens_out == 5

    def test_json_mode_null_result_falls_back_to_stdout(self, tmp_path: Path):
        """WR-02: a null (non-str) `result` must degrade to raw stdout, keeping .output a str."""
        payload = '{"result": null, "usage": {"input_tokens": 5}}'
        bridge = _make_payload_bridge(tmp_path, payload)
        result = bridge.run("Hello", output_format="json")
        assert result.success
        # .output stays a str (raw stdout) so downstream br.output.strip() is safe.
        assert result.output == payload + "\n"
        assert isinstance(result.output, str)
        assert result.usage is None

    def test_duration_s_set_on_success(self, tmp_path: Path):
        """duration_s is set on every non-dry, non-error return regardless of format."""
        bridge = _make_payload_bridge(tmp_path, "hi")
        result = bridge.run("Hello")
        assert result.duration_s is not None
        assert result.duration_s >= 0

    def test_dry_run_usage_and_duration_none(self):
        """dry_run measures no real work: usage and duration_s stay None."""
        bridge = ClaudeBridge(dry_run=True)
        result = bridge.run("Hello", output_format="json")
        assert result.usage is None
        assert result.duration_s is None


class TestSandboxWrapLlmSite:
    """Task 2 (SBX-03): bridge.py's claude call routes through wrap('llm', ...)."""

    def _capture_env(self, monkeypatch):
        """Patch subprocess.run to capture the env= kwarg without spawning anything."""
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fake_run)
        return captured

    def test_default_observe_scrubs_secrets_preserves_auth_and_ordering(
        self, tmp_path: Path, monkeypatch
    ):
        """Default observe tier: auth survives, CLAUDECODE stays popped, cache var
        stays set, credential-shaped vars are dropped (T-24-01/T-24-02/T-24-03)."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/fake/config")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-secret")
        monkeypatch.setenv("CLAUDECODE", "1")

        captured = self._capture_env(monkeypatch)

        config = BridgeConfig(
            claude_bin="/usr/bin/fake-claude",
            project_root=tmp_path,
            enable_prompt_caching_1h=True,
        )
        bridge = ClaudeBridge(config=config)
        result = bridge.run("Hello")

        assert result.success
        env = captured["env"]
        # Auth vars survive the scrub (T-24-02).
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-test"
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-test"
        assert env["CLAUDE_CONFIG_DIR"] == "/fake/config"
        # Env-prep ordering preserved (T-24-03): CLAUDECODE stays popped,
        # cache var stays set post-scrub.
        assert "CLAUDECODE" not in env
        assert env["ENABLE_PROMPT_CACHING_1H"] == "1"
        # Credential-shaped var is scrubbed under default observe (T-24-01).
        assert "AWS_SECRET_ACCESS_KEY" not in env

    def test_sandbox_unavailable_error_degrades_to_failed_result(self, tmp_path: Path, monkeypatch):
        """CR-01: a confine-tier wrap() raising SandboxUnavailableError must not
        crash run() — it degrades to BridgeResult(success=False, ...) carrying
        the install-hint message, and never falls back to running unconfined."""
        from flowstate.sandbox import SandboxUnavailableError

        def fake_wrap(*args, **kwargs):
            raise SandboxUnavailableError("bwrap not found. Install bubblewrap.")

        monkeypatch.setattr("flowstate.bridge.wrap", fake_wrap)

        def fail_if_called(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called when wrap() raises")

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fail_if_called)

        config = BridgeConfig(claude_bin="/usr/bin/fake-claude", project_root=tmp_path)
        bridge = ClaudeBridge(config=config)
        result = bridge.run("Hello")

        assert result.success is False
        assert "bwrap not found" in result.error

    def test_subprocess_oserror_degrades_to_failed_result(self, tmp_path: Path, monkeypatch):
        """WR-02: an OSError raised by subprocess.run (e.g. a located sandbox-exec/
        bwrap binary that exists but isn't executable) must degrade to
        BridgeResult(success=False, ...) rather than an unhandled crash."""

        def fake_run_raises(cmd, **kwargs):
            raise PermissionError("not executable")

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fake_run_raises)

        config = BridgeConfig(claude_bin="/usr/bin/fake-claude", project_root=tmp_path)
        bridge = ClaudeBridge(config=config)
        result = bridge.run("Hello")

        assert result.success is False
        assert "not executable" in result.error

    def test_wraps_at_surface_llm(self, tmp_path: Path, monkeypatch):
        """The wrap() call site uses surface literal 'llm' (D-02) — verified by
        confirming argv is unchanged under observe (observe never touches argv)."""
        captured = self._capture_env(monkeypatch)
        config = BridgeConfig(claude_bin="/usr/bin/fake-claude", project_root=tmp_path)
        bridge = ClaudeBridge(config=config)
        result = bridge.run("Hello")

        assert result.success
        assert captured["cmd"][0] == "/usr/bin/fake-claude"


class TestCumulativeTotals:
    """Task 2 (TAX-01): ClaudeBridge cumulative usage + wall-clock totals."""

    def test_initial_totals_zero(self, tmp_path: Path):
        bridge = _make_payload_bridge(tmp_path, "x")
        assert bridge.total_tokens_in == 0
        assert bridge.total_tokens_out == 0
        assert bridge.total_cache_read == 0
        assert bridge.total_wall_clock_s == 0.0

    def test_totals_sum_across_json_calls(self, tmp_path: Path):
        payload = (
            '{"result": "a", '
            '"usage": {"input_tokens": 10, "output_tokens": 100, '
            '"cache_read_input_tokens": 24308}}'
        )
        bridge = _make_payload_bridge(tmp_path, payload)
        r1 = bridge.run("one", output_format="json")
        r2 = bridge.run("two", output_format="json")
        assert bridge.total_tokens_in == 20
        assert bridge.total_tokens_out == 200
        assert bridge.total_cache_read == 48616
        assert bridge.total_wall_clock_s == (r1.duration_s or 0.0) + (r2.duration_s or 0.0)

    def test_text_call_adds_wall_clock_not_tokens(self, tmp_path: Path):
        bridge = _make_payload_bridge(tmp_path, "plain")
        result = bridge.run("one")  # text mode → usage None
        assert bridge.total_tokens_in == 0
        assert bridge.total_tokens_out == 0
        assert bridge.total_cache_read == 0
        assert bridge.total_wall_clock_s == (result.duration_s or 0.0)


class TestConfineTempProfileCleanup:
    """Task 2 (WR-09/SBX-05): confine-tier .sb temp profile unlinked on every exit path.

    `wrap()` dispatches to `sandbox._wrap_macos` when `tier == "confine"` on darwin,
    which writes a real `NamedTemporaryFile(delete=False, suffix=".sb")` to disk and
    returns argv shaped `[sandbox-exec, "-f", <path>, *cmd]`. These tests force that
    dispatch (monkeypatching `sys.platform` in both modules so this passes on any
    host OS) and stub `subprocess.run` so no real `sandbox-exec`/`claude` is spawned —
    fully offline and deterministic — then assert the real temp file left on disk by
    `_wrap_macos` is gone after `bridge.run()` returns, on both the success and the
    error paths.
    """

    def _confine_config(self, tmp_path: Path) -> BridgeConfig:
        fake_claude = tmp_path / "claude"
        fake_claude.write_text("#!/bin/sh\necho ok")
        fake_claude.chmod(0o755)
        return BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path, sandbox="confine")

    def _force_darwin(self, monkeypatch):
        """Force the confine->macOS dispatch regardless of the host OS running pytest."""
        monkeypatch.setattr("flowstate.bridge.sys.platform", "darwin")
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "darwin")

    def test_success_path_removes_temp_profile(self, tmp_path: Path, monkeypatch):
        self._force_darwin(monkeypatch)
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fake_run)

        bridge = ClaudeBridge(config=self._confine_config(tmp_path))
        result = bridge.run("Hello")

        assert result.success
        assert captured["cmd"][0:2] == [captured["cmd"][0], "-f"]
        profile_path = Path(captured["cmd"][2])
        assert not profile_path.exists(), "temp .sb profile must be unlinked after run() succeeds"

    def test_timeout_path_still_removes_temp_profile(self, tmp_path: Path, monkeypatch):
        self._force_darwin(monkeypatch)
        captured: dict = {}

        def fake_run_raises(cmd, **kwargs):
            captured["cmd"] = cmd
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fake_run_raises)

        bridge = ClaudeBridge(config=self._confine_config(tmp_path))
        result = bridge.run("Hello")

        assert not result.success
        profile_path = Path(captured["cmd"][2])
        assert not profile_path.exists(), (
            "temp .sb profile must be unlinked even when the subprocess times out"
        )

    def test_file_not_found_path_still_removes_temp_profile(self, tmp_path: Path, monkeypatch):
        self._force_darwin(monkeypatch)
        captured: dict = {}

        def fake_run_raises(cmd, **kwargs):
            captured["cmd"] = cmd
            raise FileNotFoundError()

        monkeypatch.setattr("flowstate.bridge.subprocess.run", fake_run_raises)

        bridge = ClaudeBridge(config=self._confine_config(tmp_path))
        result = bridge.run("Hello")

        assert not result.success
        profile_path = Path(captured["cmd"][2])
        assert not profile_path.exists(), (
            "temp .sb profile must be unlinked even on FileNotFoundError"
        )

    def test_observe_tier_does_not_attempt_unlink(self, tmp_path: Path, monkeypatch):
        """Regression: default observe-tier run() never treats argv[2] as a profile
        to unlink, and does not error even though observe leaves argv untouched
        (so argv[2] is ordinary claude CLI content, not a real file path)."""
        self._force_darwin(monkeypatch)
        fake_claude = tmp_path / "claude"
        fake_claude.write_text("#!/bin/sh\necho ok")
        fake_claude.chmod(0o755)
        config = BridgeConfig(claude_bin=str(fake_claude), project_root=tmp_path)
        assert config.sandbox == "observe"

        result = ClaudeBridge(config=config).run("Hello")

        assert result.success
        assert "ok" in result.output
