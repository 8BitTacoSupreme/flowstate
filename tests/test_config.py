"""Tests for flowstate.config — persistent default root."""

from __future__ import annotations

from pathlib import Path

import flowstate.config as config_mod


def test_load_nonexistent_returns_none(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", tmp_path / "nope" / "config.toml")
    assert config_mod.load_default_root() is None


def test_save_load_roundtrip(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_file.parent)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)

    project = tmp_path / "my_project"
    project.mkdir()

    config_mod.save_default_root(project)
    assert cfg_file.exists()

    loaded = config_mod.load_default_root()
    assert loaded == project.resolve()


def test_stale_path_returns_none(tmp_path: Path, monkeypatch):
    """If the saved path no longer exists on disk, return None."""
    cfg_file = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_file.parent)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)

    gone = tmp_path / "vanished"
    gone.mkdir()
    config_mod.save_default_root(gone)
    gone.rmdir()

    assert config_mod.load_default_root() is None


def test_clear_removes_file(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_file.parent)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)

    project = tmp_path / "proj"
    project.mkdir()
    config_mod.save_default_root(project)

    assert config_mod.clear_default_root() is True
    assert not cfg_file.exists()


def test_clear_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", tmp_path / "nope.toml")
    assert config_mod.clear_default_root() is False


def test_resolve_explicit_wins(tmp_path: Path, monkeypatch):
    """Explicit --root should beat saved config."""
    cfg_file = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_file.parent)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)

    saved_dir = tmp_path / "saved"
    saved_dir.mkdir()
    config_mod.save_default_root(saved_dir)

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()

    result = config_mod.resolve_root(explicit_dir, option_was_explicit=True)
    assert result == explicit_dir.resolve()


def test_resolve_saved_over_cwd(tmp_path: Path, monkeypatch):
    """When no explicit --root, saved config wins over cwd."""
    cfg_file = tmp_path / "cfg" / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_file.parent)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)

    saved_dir = tmp_path / "saved"
    saved_dir.mkdir()
    config_mod.save_default_root(saved_dir)

    result = config_mod.resolve_root(None, option_was_explicit=False)
    assert result == saved_dir.resolve()


def test_resolve_falls_back_to_cwd(tmp_path: Path, monkeypatch):
    """No explicit, no saved -> cwd."""
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", tmp_path / "nope.toml")
    monkeypatch.chdir(tmp_path)

    result = config_mod.resolve_root(None, option_was_explicit=False)
    assert result == tmp_path.resolve()


def test_malformed_toml_returns_none(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)
    cfg_file.write_text("not valid [ toml {{{")
    assert config_mod.load_default_root() is None
