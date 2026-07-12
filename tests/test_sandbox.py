"""Tests for flowstate.sandbox — env-scrub denylist and the wrap() seam."""

from __future__ import annotations

from flowstate.sandbox import _scrub_env

# ---------------------------------------------------------------------------
# TestScrubEnv
# ---------------------------------------------------------------------------


class TestScrubEnv:
    def test_drops_aws_prefix_match(self):
        env = _scrub_env({"AWS_SECRET_ACCESS_KEY": "x"})
        assert "AWS_SECRET_ACCESS_KEY" not in env

    def test_drops_api_key_suffix_match(self):
        env = _scrub_env({"FOO_API_KEY": "x"})
        assert "FOO_API_KEY" not in env

    def test_drops_token_suffix_match(self):
        env = _scrub_env({"SOME_TOKEN": "x"})
        assert "SOME_TOKEN" not in env

    def test_drops_exact_match(self):
        env = _scrub_env({"PASSWORD": "x"})
        assert "PASSWORD" not in env

    def test_keeps_anthropic_api_key_carve_out(self):
        env = _scrub_env({"ANTHROPIC_API_KEY": "sk-ant"})
        assert env["ANTHROPIC_API_KEY"] == "sk-ant"

    def test_keeps_claude_code_oauth_token_carve_out(self):
        env = _scrub_env({"CLAUDE_CODE_OAUTH_TOKEN": "t"})
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "t"

    def test_keeps_claude_config_dir_carve_out(self):
        env = _scrub_env({"CLAUDE_CONFIG_DIR": "/p"})
        assert env["CLAUDE_CONFIG_DIR"] == "/p"

    def test_keeps_unmatched_var_regression_guard(self):
        env = _scrub_env({"ENABLE_PROMPT_CACHING_1H": "1"})
        assert env["ENABLE_PROMPT_CACHING_1H"] == "1"

    def test_keeps_pass_through_defaults(self):
        env = _scrub_env({"PATH": "/usr/bin", "HOME": "/h"})
        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/h"

    def test_bare_anthropic_prefix_is_not_denied(self):
        # FlowState's own auth lives under ANTHROPIC_* — a bare-prefix block
        # would break the subprocess `observe` exists to protect
        # (23-RESEARCH.md Pitfall 1).
        env = _scrub_env({"ANTHROPIC_CUSTOM_HEADER": "x"})
        assert env["ANTHROPIC_CUSTOM_HEADER"] == "x"

    def test_never_mutates_input_dict(self):
        original = {"AWS_SECRET_ACCESS_KEY": "x", "PATH": "/usr/bin"}
        snapshot = dict(original)
        _scrub_env(original)
        assert original == snapshot

    def test_returns_new_dict_not_same_object(self):
        original = {"PATH": "/usr/bin"}
        result = _scrub_env(original)
        assert result is not original
