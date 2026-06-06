"""Tests for flowstate.pack — repomix locator, run_pack(), staleness check."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from flowstate.cli import main
from flowstate.pack import _find_repomix, is_pack_stale, run_pack
from flowstate.state import FlowStateModel, InstallEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fake_repomix(tmp_path: Path, *, exit_code: int = 0) -> Path:
    """Write a fake repomix shell script to tmp_path and return its path."""
    script = tmp_path / "repomix"
    if exit_code == 0:
        script.write_text(
            "#!/bin/sh\n"
            # Write a minimal sentinel XML to --output path
            'OUTPUT=""\n'
            'while [ "$#" -gt 0 ]; do\n'
            '  case "$1" in\n'
            '    --output) OUTPUT="$2"; shift 2;;\n'
            "    *) shift;;\n"
            "  esac\n"
            "done\n"
            'if [ -n "$OUTPUT" ]; then\n'
            '  echo "<?xml version=\\"1.0\\"?><repomix/>" > "$OUTPUT"\n'
            "fi\n"
            "exit 0\n"
        )
    else:
        script.write_text("#!/bin/sh\necho 'repomix error' >&2\nexit 1\n")
    script.chmod(0o755)
    return script


# ---------------------------------------------------------------------------
# TestFindRepomix
# ---------------------------------------------------------------------------


class TestFindRepomix:
    def test_env_override_returns_path_when_file_exists(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "repomix-custom"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))
        result = _find_repomix()
        assert result == str(fake)

    def test_env_override_ignored_when_file_missing(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(tmp_path / "does-not-exist"))
        monkeypatch.delenv("PATH", raising=False)
        # With no PATH and no valid env path, should return ""
        result = _find_repomix()
        assert result == ""

    def test_which_detection(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "repomix"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)

        monkeypatch.delenv("FLOWSTATE_REPOMIX_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
        result = _find_repomix()
        assert result == str(fake)

    def test_missing_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_REPOMIX_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        result = _find_repomix()
        assert result == ""


# ---------------------------------------------------------------------------
# TestRunPack
# ---------------------------------------------------------------------------


class TestRunPack:
    def test_success_writes_xml_and_registers_manifest(self, tmp_path: Path, monkeypatch):
        fake = _write_fake_repomix(tmp_path)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))

        result = run_pack(tmp_path)

        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.output_path.suffix == ".xml"

        # Manifest entry registered
        from flowstate.state import load_state

        state = load_state(tmp_path)
        pack_entries = [e for e in state.install_manifest if e.kind == "pack"]
        assert len(pack_entries) == 1
        assert pack_entries[0].checksum is not None

    def test_absent_repomix_returns_graceful_failure(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_REPOMIX_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        result = run_pack(Path("/tmp"))
        assert result.success is False
        assert result.exit_code != 0
        assert "repomix" in result.error.lower()

    def test_repomix_nonzero_exit_returns_failure(self, tmp_path: Path, monkeypatch):
        fake = _write_fake_repomix(tmp_path, exit_code=1)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))
        result = run_pack(tmp_path)
        assert result.success is False

    def test_compress_flag_included_in_argv(self, tmp_path: Path, monkeypatch):
        """run_pack(compress=True) should pass --compress to repomix."""
        # Write a repomix that records its argv to a file
        script = tmp_path / "repomix"
        argv_file = tmp_path / "argv.txt"
        script.write_text(
            f"#!/bin/sh\n"
            f'OUTPUT=""\n'
            f'while [ "$#" -gt 0 ]; do\n'
            f'  case "$1" in\n'
            f'    --output) OUTPUT="$2"; shift 2;;\n'
            f"    *) shift;;\n"
            f"  esac\n"
            f"done\n"
            f'echo "$@" >> "{argv_file}"\n'
            f'if [ -n "$OUTPUT" ]; then\n'
            f'  echo "<?xml version=\\"1.0\\"?><repomix/>" > "$OUTPUT"\n'
            f"fi\n"
            f"exit 0\n"
        )
        # Write a simpler script that just logs all args
        args_script = tmp_path / "repomix"
        args_script.write_text(
            f"#!/bin/sh\n"
            f'printf "%s\\n" "$@" > "{argv_file}"\n'
            f'OUTPUT=""\n'
            f'while [ "$#" -gt 0 ]; do\n'
            f'  case "$1" in\n'
            f'    --output) OUTPUT="$2"; shift 2;;\n'
            f"    *) shift;;\n"
            f"  esac\n"
            f"done\n"
            f'if [ -n "$OUTPUT" ]; then\n'
            f'  echo "<?xml version=\\"1.0\\"?><repomix/>" > "$OUTPUT"\n'
            f"fi\n"
            f"exit 0\n"
        )
        args_script.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(args_script))

        run_pack(tmp_path, compress=True)

        assert argv_file.exists()
        args_content = argv_file.read_text()
        assert "--compress" in args_content

    def test_compress_flag_omitted_by_default(self, tmp_path: Path, monkeypatch):
        """run_pack() without compress=True does not include --compress."""
        argv_file = tmp_path / "argv.txt"
        args_script = tmp_path / "repomix"
        args_script.write_text(
            f"#!/bin/sh\n"
            f'printf "%s\\n" "$@" > "{argv_file}"\n'
            f'OUTPUT=""\n'
            f'while [ "$#" -gt 0 ]; do\n'
            f'  case "$1" in\n'
            f'    --output) OUTPUT="$2"; shift 2;;\n'
            f"    *) shift;;\n"
            f"  esac\n"
            f"done\n"
            f'if [ -n "$OUTPUT" ]; then\n'
            f'  echo "<?xml version=\\"1.0\\"?><repomix/>" > "$OUTPUT"\n'
            f"fi\n"
            f"exit 0\n"
        )
        args_script.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(args_script))

        run_pack(tmp_path, compress=False)

        assert argv_file.exists()
        args_content = argv_file.read_text()
        assert "--compress" not in args_content


# ---------------------------------------------------------------------------
# TestIsPackStale
# ---------------------------------------------------------------------------


class TestIsPackStale:
    def _make_state_with_pack_entry(self, root: Path, created_at: datetime) -> FlowStateModel:
        state = FlowStateModel()
        rel = ".planning/codebase/repomix-pack.xml"
        state.install_manifest = [
            InstallEntry(
                path=rel,
                owner="pack",
                kind="pack",
                created_at=created_at,
                checksum="abc123",
            )
        ]
        return state

    def test_fresh_pack_not_stale(self, tmp_path: Path):
        """Pack created_at newer than source mtime → not stale."""
        import os
        import time

        src = tmp_path / "mymodule.py"
        src.write_text("# hello")

        # Back-date the source file's mtime by 30s so the pack entry is clearly newer
        old_mtime = time.time() - 30
        os.utime(src, (old_mtime, old_mtime))

        # Pack entry is "now" — newer than the backdated source file
        state = self._make_state_with_pack_entry(tmp_path, created_at=datetime.now(UTC))
        assert is_pack_stale(tmp_path, state) is False

    def test_stale_when_source_newer_than_pack(self, tmp_path: Path):
        """Source mtime > pack created_at → stale."""
        src = tmp_path / "mymodule.py"
        src.write_text("# hello")

        # Pack timestamp is in the past (before source was written)
        past = datetime.now(UTC) - timedelta(seconds=30)
        state = self._make_state_with_pack_entry(tmp_path, created_at=past)

        assert is_pack_stale(tmp_path, state) is True

    def test_stale_when_no_pack_entry(self, tmp_path: Path):
        """No pack entry in manifest → always stale."""
        state = FlowStateModel()  # empty manifest
        assert is_pack_stale(tmp_path, state) is True

    def test_not_stale_when_no_python_files(self, tmp_path: Path):
        """No *.py files found → pack not stale (nothing can be newer)."""
        future = datetime.now(UTC) + timedelta(seconds=60)
        state = self._make_state_with_pack_entry(tmp_path, created_at=future)
        assert is_pack_stale(tmp_path, state) is False


# ---------------------------------------------------------------------------
# TestPackCommand (CliRunner)
# ---------------------------------------------------------------------------


class TestPackCommand:
    def test_pack_exits_0_and_prints_pack_written(self, tmp_path: Path, monkeypatch):
        fake = _write_fake_repomix(tmp_path)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))

        runner = CliRunner()
        result = runner.invoke(main, ["pack", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "Pack written" in result.output

    def test_pack_exits_1_when_repomix_absent(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_REPOMIX_BIN", raising=False)
        monkeypatch.setenv("PATH", "")

        runner = CliRunner()
        result = runner.invoke(main, ["pack", "--root", str(tmp_path)])
        assert result.exit_code == 1
        assert "repomix" in result.output.lower()

    def test_pack_skips_when_up_to_date(self, tmp_path: Path, monkeypatch):
        """Second pack invocation on a fresh pack prints the skip message."""
        fake = _write_fake_repomix(tmp_path)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))

        runner = CliRunner()

        # First invocation — writes the pack
        result1 = runner.invoke(main, ["pack", "--root", str(tmp_path)])
        assert result1.exit_code == 0, result1.output

        # Monkeypatch is_pack_stale to return False so the skip path fires
        from flowstate import pack as pack_module

        monkeypatch.setattr(pack_module, "is_pack_stale", lambda root, state: False)

        result2 = runner.invoke(main, ["pack", "--root", str(tmp_path)])
        assert result2.exit_code == 0, result2.output
        assert "up to date" in result2.output.lower() or "skipping" in result2.output.lower()

    def test_pack_force_repacks_even_when_fresh(self, tmp_path: Path, monkeypatch):
        """--force bypasses the staleness check and always repacks."""
        fake = _write_fake_repomix(tmp_path)
        monkeypatch.setenv("FLOWSTATE_REPOMIX_BIN", str(fake))

        runner = CliRunner()

        # First invocation
        runner.invoke(main, ["pack", "--root", str(tmp_path)])

        from flowstate import pack as pack_module

        monkeypatch.setattr(pack_module, "is_pack_stale", lambda root, state: False)

        # With --force, should still pack
        result = runner.invoke(main, ["pack", "--root", str(tmp_path), "--force"])
        assert result.exit_code == 0, result.output
        assert "Pack written" in result.output
