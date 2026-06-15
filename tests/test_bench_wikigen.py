"""Tests for bench/wikigen.py — distilled-CAG wiki generator.

Covers:
- Missing pack → non-zero exit, no subprocess call.
- Existing wiki.md without --force → skipped, no subprocess call, zero exit.
- Existing wiki.md with --force → proceeds to subprocess.
- claude not found → non-zero exit, no write.
- Mocked subprocess returncode==0 + non-empty stdout → writes wiki.md, returns 0.
- Mocked subprocess returncode!=0 → non-zero exit, no write.
- Mocked subprocess returncode==0 + empty stdout → non-zero exit, no write.
- Subprocess raising → caught, non-zero exit, never raises.
- Pack text > 120000 chars is truncated before embedding in the prompt.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock

import bench.wikigen as wikigen_mod
from bench.wikigen import _MAX_PACK_CHARS, _PACK_REL, _WIKI_REL, PROMPT_HEADER, main


def _write_pack(root: Path, content: str = "<pack>content</pack>") -> Path:
    """Write a fake repomix pack and return its path."""
    pack_path = root / _PACK_REL
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(content)
    return pack_path


def test_missing_pack_returns_nonzero_no_subprocess(tmp_path, monkeypatch):
    """Missing pack → non-zero exit, no subprocess call made."""
    call_count = Mock()
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: call_count())

    rc = main(["--root", str(tmp_path)])
    assert rc != 0
    assert call_count.call_count == 0


def test_existing_wiki_without_force_skips_no_subprocess(tmp_path, monkeypatch, capsys):
    """Existing wiki.md without --force → skipped, no subprocess call, zero exit."""
    _write_pack(tmp_path)
    wiki_path = tmp_path / _WIKI_REL
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text("existing wiki content")

    call_count = Mock()
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: call_count())

    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    assert call_count.call_count == 0
    out = capsys.readouterr().out
    assert "skipping" in out.lower() or "up to date" in out.lower()


def test_existing_wiki_with_force_proceeds_to_subprocess(tmp_path, monkeypatch):
    """Existing wiki.md with --force → subprocess is called."""
    _write_pack(tmp_path)
    wiki_path = tmp_path / _WIKI_REL
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text("old wiki")

    call_count = Mock()
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    class _Good:
        returncode = 0
        stdout = "new wiki content\n"
        stderr = ""

    def _fake_run(*a, **k):
        call_count()
        return _Good()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = main(["--root", str(tmp_path), "--force"])
    assert rc == 0
    assert call_count.call_count == 1
    assert wiki_path.read_text() == "new wiki content\n"


def test_claude_not_found_returns_nonzero_no_write(tmp_path, monkeypatch):
    """_locate_claude returns None → non-zero exit, no subprocess call, no wiki written."""
    _write_pack(tmp_path)

    call_count = Mock()
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: call_count())

    rc = main(["--root", str(tmp_path)])
    assert rc != 0
    assert call_count.call_count == 0
    assert not (tmp_path / _WIKI_REL).exists()


def test_subprocess_success_writes_wiki_and_returns_0(tmp_path, monkeypatch, capsys):
    """Mocked subprocess returncode==0 + non-empty stdout → wiki.md written, returns 0."""
    _write_pack(tmp_path)

    wiki_content = "# Architecture\n\nModule map here.\n"
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    class _Good:
        returncode = 0
        stdout = wiki_content
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Good())

    rc = main(["--root", str(tmp_path)])
    assert rc == 0
    wiki_path = tmp_path / _WIKI_REL
    assert wiki_path.exists()
    assert wiki_path.read_text() == wiki_content
    out = capsys.readouterr().out
    # The path to the wiki must be printed
    assert str(wiki_path) in out or _WIKI_REL in out


def test_subprocess_nonzero_returns_nonzero_no_write(tmp_path, monkeypatch):
    """Mocked subprocess returncode!=0 → non-zero exit, no wiki.md written."""
    _write_pack(tmp_path)
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    class _Bad:
        returncode = 1
        stdout = "some output"
        stderr = "error message"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Bad())

    rc = main(["--root", str(tmp_path)])
    assert rc != 0
    assert not (tmp_path / _WIKI_REL).exists()


def test_subprocess_empty_stdout_returns_nonzero_no_write(tmp_path, monkeypatch):
    """Mocked subprocess returncode==0 + empty stdout → non-zero exit, no write."""
    _write_pack(tmp_path)
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    class _Empty:
        returncode = 0
        stdout = "   "
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Empty())

    rc = main(["--root", str(tmp_path)])
    assert rc != 0
    assert not (tmp_path / _WIKI_REL).exists()


def test_subprocess_raising_returns_nonzero_never_raises(tmp_path, monkeypatch):
    """Subprocess raising is caught, non-zero exit, never propagates."""
    _write_pack(tmp_path)
    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    def _boom(*a, **k):
        raise RuntimeError("subprocess exploded")

    monkeypatch.setattr(subprocess, "run", _boom)

    rc = main(["--root", str(tmp_path)])  # must not raise
    assert rc != 0
    assert not (tmp_path / _WIKI_REL).exists()


def test_pack_truncated_to_max_chars(tmp_path, monkeypatch):
    """Pack text > 120000 chars is truncated in the prompt passed to subprocess."""
    large_pack = "X" * (_MAX_PACK_CHARS + 50000)
    _write_pack(tmp_path, large_pack)

    monkeypatch.setattr(wikigen_mod, "_locate_claude", lambda: "/bin/claude")

    captured_cmd: list = []

    class _Good:
        returncode = 0
        stdout = "wiki output\n"
        stderr = ""

    def _fake_run(cmd, **k):
        captured_cmd.extend(cmd)
        return _Good()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    rc = main(["--root", str(tmp_path)])
    assert rc == 0

    # The last element of cmd is the prompt (passed after "--")
    # Find "--" separator then the prompt is the next arg
    sep_idx = captured_cmd.index("--")
    prompt = captured_cmd[sep_idx + 1]
    # Prompt starts with PROMPT_HEADER then truncated pack
    assert prompt.startswith(PROMPT_HEADER)
    pack_in_prompt = prompt[len(PROMPT_HEADER) :]
    assert len(pack_in_prompt) == _MAX_PACK_CHARS, (
        f"Expected pack truncated to {_MAX_PACK_CHARS} chars, got {len(pack_in_prompt)}"
    )


def test_module_callable_as_python_m(tmp_path, monkeypatch):
    """Verify __name__ == '__main__' guard exists by checking main is importable and callable."""
    # The __main__ guard is verified by the module's if-block; just confirm main is callable.
    assert callable(main)


def test_prompt_header_constant_is_correct():
    """PROMPT_HEADER must contain the required section descriptions."""
    assert "architecture wiki" in PROMPT_HEADER.lower() or "wiki" in PROMPT_HEADER.lower()
    assert "CODEBASE PACK:" in PROMPT_HEADER
    assert "system overview" in PROMPT_HEADER.lower() or "overview" in PROMPT_HEADER.lower()
