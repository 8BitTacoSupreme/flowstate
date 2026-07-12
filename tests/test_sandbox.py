"""Tests for flowstate.sandbox — env-scrub denylist and the wrap() seam."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

from flowstate.sandbox import (
    _apply_landlock,
    _find_bwrap,
    _find_sandbox_exec,
    _landlock_available,
    _scrub_env,
    _wrap_linux,
    _wrap_macos,
    build_linux_bwrap_args,
    build_macos_profile,
    check_bwrap_available,
    wrap,
)

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

    def test_unrecognized_tier_value_degrades_to_observe(self, monkeypatch):
        # WR-01: a typo'd/unrecognized tier string must fail SAFE to observe,
        # not fall through into real confinement dispatch. Force the platform
        # branch to darwin so a bug here would be caught even on this dev
        # machine (a mis-dispatch would try to build a real sandbox-exec
        # profile instead of returning the plain passthrough).
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "darwin")
        argv = ["echo", "hi"]
        env = {"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "leak"}
        new_argv, new_env = wrap(argv, "llm", Path("/tmp/p"), env, tier="Confine")
        assert new_argv == argv
        assert new_env == _scrub_env(env)


# ---------------------------------------------------------------------------
# TestBuildMacosProfile
# ---------------------------------------------------------------------------


class TestBuildMacosProfile:
    def test_matches_spike_proven_shape(self, tmp_path: Path):
        profile = build_macos_profile(tmp_path)
        assert profile == (
            "(version 1)\n"
            "(allow default)\n"
            "(deny file-write*)\n"
            "(allow file-write*\n"
            f'  (subpath "{tmp_path}")\n'
            '  (subpath "/private/tmp")\n'
            '  (subpath "/private/var/folders")\n'
            '  (subpath "/dev"))\n'
            f'(deny file-read* (subpath "{Path.home() / ".ssh"}"))\n'
        )

    def test_deterministic_same_project_root_byte_identical(self, tmp_path: Path):
        assert build_macos_profile(tmp_path) == build_macos_profile(tmp_path)

    def test_contains_allow_default_baseline(self, tmp_path: Path):
        assert "(allow default)" in build_macos_profile(tmp_path)

    def test_contains_deny_file_write_baseline(self, tmp_path: Path):
        assert "(deny file-write*)" in build_macos_profile(tmp_path)

    def test_project_root_embedded_verbatim_in_subpath_quotes(self, tmp_path: Path):
        # T-23-04: project_root is embedded as-is inside the subpath quotes;
        # metacharacter hardening is a Phase-25 confine-runtime concern.
        profile = build_macos_profile(tmp_path)
        assert f'(subpath "{tmp_path}")' in profile

    def test_denies_ssh_read(self, tmp_path: Path):
        profile = build_macos_profile(tmp_path)
        assert ".ssh" in profile
        assert "(deny file-read*" in profile


# ---------------------------------------------------------------------------
# TestFindSandboxExec
# ---------------------------------------------------------------------------


class TestFindSandboxExec:
    def test_env_override_returns_path_when_file_exists(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "sandbox-exec-custom"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.setenv("FLOWSTATE_SANDBOX_EXEC_BIN", str(fake))
        assert _find_sandbox_exec() == str(fake)

    def test_env_override_ignored_when_file_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_SANDBOX_EXEC_BIN", str(tmp_path / "does-not-exist"))
        monkeypatch.delenv("PATH", raising=False)
        assert _find_sandbox_exec() == "/usr/bin/sandbox-exec"

    def test_which_detection(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "sandbox-exec"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.delenv("FLOWSTATE_SANDBOX_EXEC_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
        assert _find_sandbox_exec() == str(fake)

    def test_fallback_when_absent(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_SANDBOX_EXEC_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        assert _find_sandbox_exec() == "/usr/bin/sandbox-exec"


# ---------------------------------------------------------------------------
# TestWrapMacos
# ---------------------------------------------------------------------------


class TestWrapMacos:
    def test_argv_prefixed_with_sandbox_exec_and_flag(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_SANDBOX_EXEC_BIN", "/usr/bin/sandbox-exec")
        cmd = ["claude", "--print"]
        argv, _ = _wrap_macos(cmd, tmp_path, {"PATH": "/b"})
        assert argv[0] == "/usr/bin/sandbox-exec"
        assert argv[1] == "-f"

    def test_argv_suffix_matches_original_cmd(self, tmp_path: Path):
        cmd = ["claude", "--print"]
        argv, _ = _wrap_macos(cmd, tmp_path, {"PATH": "/b"})
        assert argv[3:] == cmd

    def test_temp_profile_file_exists_and_matches_build_macos_profile(self, tmp_path: Path):
        cmd = ["claude", "--print"]
        argv, _ = _wrap_macos(cmd, tmp_path, {"PATH": "/b"})
        profile_path = Path(argv[2])
        assert profile_path.exists()
        assert profile_path.read_text() == build_macos_profile(tmp_path)

    def test_env_unchanged(self, tmp_path: Path):
        env = {"PATH": "/b"}
        _, new_env = _wrap_macos(["claude", "--print"], tmp_path, env)
        assert new_env == {"PATH": "/b"}


# ---------------------------------------------------------------------------
# TestBuildLinuxBwrapArgs
# ---------------------------------------------------------------------------


class TestBuildLinuxBwrapArgs:
    def test_matches_golden_shape(self, tmp_path: Path):
        project = str(tmp_path)
        ssh_dir = str(Path.home() / ".ssh")
        assert build_linux_bwrap_args(tmp_path) == [
            "--ro-bind",
            "/",
            "/",
            "--bind",
            project,
            project,
            "--tmpfs",
            ssh_dir,
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--unshare-pid",
            "--unshare-uts",
            "--unshare-ipc",
            "--die-with-parent",
        ]

    def test_deterministic_same_project_root_equal_list(self, tmp_path: Path):
        assert build_linux_bwrap_args(tmp_path) == build_linux_bwrap_args(tmp_path)

    def test_project_root_appears_exactly_once_as_bind_pair(self, tmp_path: Path):
        args = build_linux_bwrap_args(tmp_path)
        assert args.count(str(tmp_path)) == 2

    def test_contains_die_with_parent_and_unshare_flags(self, tmp_path: Path):
        args = build_linux_bwrap_args(tmp_path)
        assert "--die-with-parent" in args
        assert "--unshare-pid" in args
        assert "--unshare-uts" in args
        assert "--unshare-ipc" in args

    def test_contains_tmpfs_ssh_shadow(self, tmp_path: Path):
        args = build_linux_bwrap_args(tmp_path)
        idx = args.index("--tmpfs")
        assert args[idx + 1] == str(Path.home() / ".ssh")

    def test_does_not_contain_bwrap_binary_or_separator(self, tmp_path: Path):
        args = build_linux_bwrap_args(tmp_path)
        assert "bwrap" not in args
        assert "--" not in args


# ---------------------------------------------------------------------------
# TestLandlockAvailable
# ---------------------------------------------------------------------------


class TestLandlockAvailable:
    def test_returns_false_on_non_linux_without_raising(self):
        # This suite runs on Darwin — _landlock_available() must degrade to
        # False rather than raise (never-raise degradation contract).
        assert _landlock_available() is False


# ---------------------------------------------------------------------------
# TestApplyLandlock
# ---------------------------------------------------------------------------


class TestApplyLandlock:
    def test_noop_on_non_linux_returns_none_without_raising(self, tmp_path: Path):
        assert _apply_landlock(tmp_path) is None


# ---------------------------------------------------------------------------
# TestFindBwrap
# ---------------------------------------------------------------------------


class TestFindBwrap:
    def test_env_override_returns_path_when_file_exists(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "bwrap-custom"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.setenv("FLOWSTATE_BWRAP_BIN", str(fake))
        assert _find_bwrap() == str(fake)

    def test_env_override_ignored_when_file_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_BWRAP_BIN", str(tmp_path / "does-not-exist"))
        monkeypatch.delenv("PATH", raising=False)
        assert _find_bwrap() == ""

    def test_which_detection(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "bwrap"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.delenv("FLOWSTATE_BWRAP_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
        assert _find_bwrap() == str(fake)

    def test_fallback_empty_string_when_absent(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_BWRAP_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        assert _find_bwrap() == ""


# ---------------------------------------------------------------------------
# TestCheckBwrapAvailable
# ---------------------------------------------------------------------------


class TestCheckBwrapAvailable:
    def test_check_bwrap_available_false_when_absent(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: None)
        assert check_bwrap_available() is False

    def test_true_when_smoke_test_returncode_zero(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(
            "flowstate.sandbox.subprocess.run",
            lambda *a, **k: mock.Mock(returncode=0),
        )
        assert check_bwrap_available() is True

    def test_false_when_smoke_test_nonzero_returncode(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr(
            "flowstate.sandbox.subprocess.run",
            lambda *a, **k: mock.Mock(returncode=1),
        )
        assert check_bwrap_available() is False

    def test_false_on_oserror_never_raises(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: "/usr/bin/bwrap")

        def _raise(*a, **k):
            raise OSError("boom")

        monkeypatch.setattr("flowstate.sandbox.subprocess.run", _raise)
        assert check_bwrap_available() is False

    def test_false_on_timeout_never_raises(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: "/usr/bin/bwrap")

        def _raise(*a, **k):
            raise subprocess.TimeoutExpired(cmd="bwrap", timeout=5)

        monkeypatch.setattr("flowstate.sandbox.subprocess.run", _raise)
        assert check_bwrap_available() is False

    def test_smoke_test_invokes_ro_bind_bin_true(self, monkeypatch):
        captured: dict[str, list[str]] = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return mock.Mock(returncode=0)

        monkeypatch.setattr("flowstate.sandbox.shutil.which", lambda name: "/usr/bin/bwrap")
        monkeypatch.setattr("flowstate.sandbox.subprocess.run", _fake_run)
        check_bwrap_available()
        assert captured["cmd"] == ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"]


# ---------------------------------------------------------------------------
# TestWrapLinux
# ---------------------------------------------------------------------------


class TestWrapLinux:
    def test_wrap_linux_full_confine(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.check_bwrap_available", lambda: True)
        monkeypatch.setattr("flowstate.sandbox._landlock_available", lambda: True)
        monkeypatch.setattr("flowstate.sandbox._find_bwrap", lambda: "/usr/bin/bwrap")
        cmd = ["claude", "--print"]
        argv, env = _wrap_linux(cmd, tmp_path, {"PATH": "/b"})

        assert argv[0] == "/usr/bin/bwrap"
        assert argv.count("--") == 2  # bwrap's separator + the landlock shim's separator
        assert "--apply-landlock" in argv
        assert str(tmp_path) in argv
        assert argv[-len(cmd) :] == cmd
        assert env == {"PATH": "/b"}

    def test_wrap_linux_bwrap_only(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.check_bwrap_available", lambda: True)
        monkeypatch.setattr("flowstate.sandbox._landlock_available", lambda: False)
        monkeypatch.setattr("flowstate.sandbox._find_bwrap", lambda: "/usr/bin/bwrap")
        cmd = ["claude", "--print"]
        argv, env = _wrap_linux(cmd, tmp_path, {"PATH": "/b"})

        assert argv[0] == "/usr/bin/bwrap"
        assert argv.count("--") == 1
        assert "--apply-landlock" not in argv
        assert argv[-len(cmd) :] == cmd
        assert env == {"PATH": "/b"}

    def test_wrap_linux_falls_back_to_observe(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.check_bwrap_available", lambda: False)
        cmd = ["claude", "--print"]
        env = {"PATH": "/b"}
        argv, new_env = _wrap_linux(cmd, tmp_path, env)

        assert argv == cmd
        assert new_env == env

    def test_wrap_linux_observe_fallback_never_raises(self, tmp_path: Path):
        with mock.patch("flowstate.sandbox.check_bwrap_available", return_value=False):
            argv, env = _wrap_linux(["claude"], tmp_path, {"X": "1"})
        assert argv == ["claude"]
        assert env == {"X": "1"}

    def test_wrap_linux_observe_fallback_emits_one_time_warning(
        self, tmp_path: Path, monkeypatch, capsys
    ):
        import flowstate.sandbox as sandbox_module

        monkeypatch.setattr(sandbox_module, "check_bwrap_available", lambda: False)
        monkeypatch.setattr(sandbox_module, "_bwrap_warning_emitted", False)
        sandbox_module._wrap_linux(["claude"], tmp_path, {})
        captured = capsys.readouterr()
        assert "bwrap unavailable" in captured.err
