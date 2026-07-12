"""Tests for flowstate.sandbox — env-scrub denylist and the wrap() seam."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from flowstate.sandbox import (
    SandboxUnavailableError,
    _apply_landlock,
    _escape_sbpl_string,
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

    def test_case_insensitive_prefix_match_lowercase(self):
        # WR-08: lower/mixed-case credential-shaped vars must still be
        # caught by the denylist, not silently bypass it.
        env = _scrub_env({"aws_secret_access_key": "x"})
        assert "aws_secret_access_key" not in env

    def test_case_insensitive_suffix_match_mixed_case(self):
        env = _scrub_env({"Foo_Api_Key": "x"})
        assert "Foo_Api_Key" not in env

    def test_case_insensitive_exact_match(self):
        env = _scrub_env({"password": "x"})
        assert "password" not in env

    def test_lowercase_variant_of_exempt_name_is_not_exempted(self):
        # WR-08 fix note: _AUTH_EXEMPT matching stays exact-case (only the
        # canonical uppercase env var names claude/FlowState actually use
        # are exempted) — a lowercase variant is not the real auth var and
        # correctly falls through to the (now case-insensitive) denylist.
        env = _scrub_env({"anthropic_api_key": "leak"})
        assert "anthropic_api_key" not in env


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

    def test_unsupported_platform_observe_still_returns_scrubbed(self, monkeypatch):
        # D-01/SBX-06 (Phase 25): the observe tier is untouched — it must
        # still never raise, even on a platform with no confine mechanism.
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "sunos5")
        env = {"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "leak"}
        argv, new_env = wrap(["echo", "hi"], "llm", Path("/tmp/p"), env, tier="observe")
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
# TestWrapConfineFailLoud (D-01/SBX-06)
# ---------------------------------------------------------------------------


class TestWrapConfineFailLoud:
    def test_confine_raises_on_unsupported_platform(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "sunos5")
        with pytest.raises(SandboxUnavailableError):
            wrap(["echo", "hi"], "llm", Path("/tmp/p"), {"PATH": "/usr/bin"}, tier="confine")

    def test_confine_raises_on_linux_when_bwrap_unavailable(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.check_bwrap_available", lambda: False)
        with pytest.raises(SandboxUnavailableError) as exc_info:
            wrap(["echo", "hi"], "llm", tmp_path, {"PATH": "/usr/bin"}, tier="confine")
        assert "bwrap" in str(exc_info.value)
        assert "FLOWSTATE_BWRAP_BIN" in str(exc_info.value)

    def test_confine_raises_on_darwin_when_sandbox_exec_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "darwin")
        monkeypatch.setattr(
            "flowstate.sandbox._find_sandbox_exec", lambda: str(tmp_path / "no-such-binary")
        )
        with pytest.raises(SandboxUnavailableError) as exc_info:
            wrap(["echo", "hi"], "llm", tmp_path, {"PATH": "/usr/bin"}, tier="confine")
        assert "sandbox-exec" in str(exc_info.value)
        assert "FLOWSTATE_SANDBOX_EXEC_BIN" in str(exc_info.value)

    def test_confine_does_not_raise_on_linux_bwrap_only_partial_capability(
        self, tmp_path: Path, monkeypatch
    ):
        # Partial capability (bwrap present, landlock absent) still degrades
        # WITHIN confinement (RUNG-1 -> RUNG-2) — must NOT raise.
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.check_bwrap_available", lambda: True)
        monkeypatch.setattr("flowstate.sandbox._landlock_available", lambda: False)
        monkeypatch.setattr("flowstate.sandbox._find_bwrap", lambda: "/usr/bin/bwrap")
        argv, env = wrap(["claude", "--print"], "llm", tmp_path, {"PATH": "/b"}, tier="confine")
        assert argv[0] == "/usr/bin/bwrap"
        assert env == {"PATH": "/b"}

    def test_observe_never_raises_on_unsupported_platform_regression_guard(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "sunos5")
        argv, _env = wrap(
            ["echo", "hi"], "llm", Path("/tmp/p"), {"PATH": "/usr/bin"}, tier="observe"
        )
        assert argv == ["echo", "hi"]


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
        # T-23-04: an ordinary path (no SBPL metacharacters) has nothing to
        # escape, so it still appears verbatim inside the subpath quotes.
        # See test_project_root_with_quote_is_escaped_not_injected for the
        # hostile-path case (WR-02).
        profile = build_macos_profile(tmp_path)
        assert f'(subpath "{tmp_path}")' in profile

    def test_denies_ssh_read(self, tmp_path: Path):
        profile = build_macos_profile(tmp_path)
        assert ".ssh" in profile
        assert "(deny file-read*" in profile

    def test_project_root_with_quote_is_escaped_not_injected(self):
        # WR-02: a project_root containing a literal `"` must not terminate
        # the SBPL string early / inject additional clauses.
        hostile = Path('/tmp/evil") (allow file-write* (subpath "/')
        profile = build_macos_profile(hostile)
        escaped = _escape_sbpl_string(str(hostile))
        assert f'(subpath "{escaped}")' in profile
        # The raw, unescaped hostile string must not appear quoted verbatim.
        assert f'(subpath "{hostile}")' not in profile

    def test_project_root_with_backslash_is_escaped(self):
        hostile = Path("/tmp/weird\\path")
        profile = build_macos_profile(hostile)
        escaped = _escape_sbpl_string(str(hostile))
        assert f'(subpath "{escaped}")' in profile


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

    # WR-05: the kernel-parsing and ctypes ABI-probe branches only run when
    # sys.platform starts with "linux" — monkeypatch it (and the calls the
    # branch makes) to exercise them from this Darwin dev machine, mirroring
    # the pattern _wrap_linux's own tests already use.

    def test_returns_false_below_minimum_kernel_version(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "5.10.0-generic")
        assert _landlock_available() is False

    def test_returns_false_on_malformed_kernel_release_string(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "not-a-version")
        assert _landlock_available() is False

    def test_returns_false_when_ctypes_cdll_raises(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "6.8.0-generic")

        def _raise(*_a, **_k):
            raise OSError("no libc")

        monkeypatch.setattr("flowstate.sandbox.ctypes.CDLL", _raise)
        assert _landlock_available() is False

    def test_returns_false_when_syscall_returns_non_positive_version(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "6.8.0-generic")
        fake_libc = mock.Mock()
        fake_libc.syscall.return_value = -1
        monkeypatch.setattr("flowstate.sandbox.ctypes.CDLL", lambda *a, **k: fake_libc)
        assert _landlock_available() is False

    def test_returns_true_when_kernel_and_abi_probe_succeed(self, monkeypatch):
        monkeypatch.setattr("flowstate.sandbox.sys.platform", "linux")
        monkeypatch.setattr("flowstate.sandbox.platform.release", lambda: "6.8.0-generic")
        fake_libc = mock.Mock()
        fake_libc.syscall.return_value = 6
        monkeypatch.setattr("flowstate.sandbox.ctypes.CDLL", lambda *a, **k: fake_libc)
        assert _landlock_available() is True


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


# ---------------------------------------------------------------------------
# TestMainShim
# ---------------------------------------------------------------------------


class TestMainShim:
    # WR-06: the __main__ shim is the actual RUNG-1 code path that applies
    # Landlock before exec-ing the real target inside the confined child —
    # the single most security-critical path in the module, previously
    # untested. `_apply_landlock` no-ops on non-Linux, so invoking the shim
    # as a real subprocess is portable to this (non-Linux) dev machine.

    def test_apply_landlock_shim_execs_target_command(self, tmp_path: Path):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flowstate.sandbox",
                "--apply-landlock",
                str(tmp_path),
                "--",
                sys.executable,
                "-c",
                "print('ok')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_apply_landlock_shim_propagates_target_exit_code(self, tmp_path: Path):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flowstate.sandbox",
                "--apply-landlock",
                str(tmp_path),
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(7)",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 7
