"""Vendored-skill installer — copies flowstate/skills/* into a project's .claude/skills/.

Pure Python (stdlib ``shutil``). Skills are copied as DATA — never imported or executed.

Design notes:
- Idempotent: re-running is safe and never duplicates or corrupts the tree.
- Path-safe: every destination is asserted to resolve inside ``root/.claude/skills``;
  overwrites are scoped to the vendored namespaces only, so user-authored skills in
  sibling dirs under ``.claude/skills/`` are never clobbered. Source symlinks are skipped.
- Extensible: the copy is driven by an explicit ``_NAMESPACES`` list of
  ``(source_subdir, dest_namespace)`` pairs, so Phase 15 adds GSD by extending the list
  rather than rewriting the copy logic.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import flowstate
from flowstate.state import FlowStateModel, InstallEntry

# (source_subdir under flowstate/skills, dest_namespace under .claude/skills).
# Phase 15 appends its GSD pair here — no other change to the copy logic needed.
_NAMESPACES: list[tuple[str, str]] = [
    ("gstack", "gstack"),
    ("superpowers", "superpowers"),
]


def _skills_source() -> Path:
    """Resolve the vendored skills source tree shipped inside the package."""
    return Path(flowstate.__file__).parent / "skills"


def _copy_tree(src_dir: Path, dest_dir: Path) -> None:
    """Copy ``src_dir`` onto ``dest_dir`` as data, skipping symlinks.

    Uses ``shutil.copytree(symlinks=False)`` with an ignore callback that drops any
    symlink encountered in the source, so a symlink can never be followed out of the
    tree. ``dirs_exist_ok=True`` makes re-installs idempotent.
    """

    def _ignore_symlinks(dirpath: str, names: list[str]) -> set[str]:
        base = Path(dirpath)
        return {name for name in names if (base / name).is_symlink()}

    shutil.copytree(
        src_dir,
        dest_dir,
        dirs_exist_ok=True,
        symlinks=False,
        ignore=_ignore_symlinks,
    )


def _register(state: FlowStateModel, rel_path: str) -> None:
    """Add or replace a dir-level InstallEntry for a vendored namespace.

    Mirrors context._register's idempotence: drop any existing entry for the same
    relative path, then append. Dir entries carry checksum=None (a dir has no digest).
    """
    state.install_manifest = [e for e in state.install_manifest if e.path != rel_path]
    state.install_manifest.append(
        InstallEntry(
            path=rel_path,
            owner="skills",
            kind="artifact",
            created_at=datetime.now(UTC),
            checksum=None,
        )
    )


def install_skills(
    root: Path,
    *,
    dry_run: bool = False,
    state: FlowStateModel | None = None,
) -> list[Path]:
    """Copy the vendored skill trees into ``root/.claude/skills/``.

    Returns the list of top-level installed namespace paths (the paths that WOULD be
    written when ``dry_run`` is True). When ``state`` is provided and not a dry run,
    records one dir-level ``artifact`` InstallEntry per installed namespace.
    """
    source = _skills_source()
    skills_root = (root / ".claude" / "skills").resolve()

    installed: list[Path] = []
    for source_subdir, dest_namespace in _NAMESPACES:
        src_dir = source / source_subdir
        if not src_dir.is_dir():
            continue

        dest_dir = (skills_root / dest_namespace).resolve()
        # Path-safety: the destination must stay inside root/.claude/skills.
        if skills_root != dest_dir and skills_root not in dest_dir.parents:
            raise ValueError(f"refusing to write outside .claude/skills: {dest_dir}")

        installed.append(dest_dir)
        if dry_run:
            continue

        _copy_tree(src_dir, dest_dir)
        if state is not None:
            _register(state, f".claude/skills/{dest_namespace}")

    return installed
