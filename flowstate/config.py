"""Persistent global config for FlowState (default root, etc.)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "flowstate"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"


def load_default_root() -> Path | None:
    """Read the saved default root from config.toml.

    Returns None if the file doesn't exist or the saved path no longer
    exists on disk (prevents stale config breakage).
    """
    if not _CONFIG_FILE.exists():
        return None
    try:
        data = tomllib.loads(_CONFIG_FILE.read_text())
    except Exception:
        return None
    raw = data.get("default_root")
    if not raw:
        return None
    p = Path(raw)
    if not p.is_dir():
        return None
    return p


def save_default_root(root: Path) -> None:
    """Write the resolved absolute path as the default root."""
    resolved = root.resolve()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(f'default_root = "{resolved}"\n')


def clear_default_root() -> bool:
    """Delete the config file. Returns True if something was cleared."""
    if _CONFIG_FILE.exists():
        _CONFIG_FILE.unlink()
        return True
    return False


def resolve_root(root_option: Path | None, *, option_was_explicit: bool) -> Path:
    """Resolve project root: explicit --root > saved config > cwd."""
    if option_was_explicit and root_option is not None:
        return root_option.resolve()
    saved = load_default_root()
    if saved is not None:
        return saved
    if root_option is not None:
        return root_option.resolve()
    return Path.cwd()
