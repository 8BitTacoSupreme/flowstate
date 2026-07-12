"""Tests for flowstate.sandbox — env-scrub denylist and the wrap() seam."""

from __future__ import annotations

from pathlib import Path

from flowstate.sandbox import _scrub_env, wrap

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


# ---------------------------------------------------------------------------
# TestWrapObserve
# ---------------------------------------------------------------------------


class TestWrapObserve:
    def test_argv_byte_identical_under_default_tier(self):
        argv = ["echo", "hi"]
        new_argv, _ = wrap(argv, "llm", Path("/tmp/p"), {"PATH": "/usr/bin"})
        assert new_argv == argv

    def test_default_tier_equals_observe_env_matches_scrub_env(self):
        env = {"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "leak"}
        _, new_env = wrap(["echo", "hi"], "llm", Path("/tmp/p"), env)
        assert new_env == _scrub_env(env)

    def test_observe_never_strips_claude_auth_vars(self):
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-should-survive",
            "CLAUDE_CODE_OAUTH_TOKEN": "should-also-survive",
            "AWS_SECRET_ACCESS_KEY": "leak-me-not",
        }
        _, new_env = wrap(["echo", "hi"], "llm", Path("/tmp/p"), env)
        assert new_env["ANTHROPIC_API_KEY"] == "sk-ant-should-survive"
        assert new_env["CLAUDE_CODE_OAUTH_TOKEN"] == "should-also-survive"
        assert "AWS_SECRET_ACCESS_KEY" not in new_env

    def test_observe_never_mutates_argv(self):
        argv = ["echo", "hi"]
        original = list(argv)
        wrap(argv, "llm", Path("/tmp/p"), {"PATH": "/usr/bin"})
        assert argv == original

    def test_unsupported_platform_confine_returns_scrubbed(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "sunos5")
        env = {"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "leak"}
        argv, new_env = wrap(["echo", "hi"], "llm", Path("/tmp/p"), env, tier="confine")
        assert argv == ["echo", "hi"]
        assert new_env == _scrub_env(env)
