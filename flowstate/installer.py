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

import json
import re
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

# ── GSD (Phase 15) ────────────────────────────────────────────────────────────
# The vendored GSD distribution lives under flowstate/vendor/gsd/ (see 15-01). It
# is laid down UNCONDITIONALLY — no detect gate, no prompt. Two tree copies plus a
# per-command skill conversion cover the whole surface:
#
#   1. the get-shit-done runtime  -> .claude/get-shit-done/
#   2. the full node_modules      -> .claude/get-shit-done/node_modules/
#      (carries get-shit-done-cc + its ~90 deps, so `node <bin>/gsd-sdk.js` resolves
#      @anthropic-ai/claude-agent-sdk + ws by walking up to this node_modules)
#   3. commands/gsd/*.md          -> .claude/skills/gsd-<cmd>/SKILL.md (converted)
#
# gsd-sdk is invoked via `node <path>`; vendored code is copied as DATA and NEVER
# executed during install (no postinstall, no nested npm).
_GSD_PKG = "node_modules/get-shit-done-cc"

# (source_subpath under flowstate/vendor/gsd, dest_relpath under .claude).
_GSD_TREE_MAPPINGS: list[tuple[str, str]] = [
    (f"{_GSD_PKG}/get-shit-done", "get-shit-done"),
    ("node_modules", "get-shit-done/node_modules"),
]


def _skills_source() -> Path:
    """Resolve the vendored skills source tree shipped inside the package."""
    return Path(flowstate.__file__).parent / "skills"


def _vendor_gsd_source() -> Path:
    """Resolve the vendored GSD distribution shipped inside the package."""
    return Path(flowstate.__file__).parent / "vendor" / "gsd"


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


def _register(state: FlowStateModel, rel_path: str, owner: str = "skills") -> None:
    """Add or replace a dir-level InstallEntry for a vendored namespace.

    Mirrors context._register's idempotence: drop any existing entry for the same
    relative path, then append. Dir entries carry checksum=None (a dir has no digest).
    """
    state.install_manifest = [e for e in state.install_manifest if e.path != rel_path]
    state.install_manifest.append(
        InstallEntry(
            path=rel_path,
            owner=owner,
            kind="artifact",
            created_at=datetime.now(UTC),
            checksum=None,
        )
    )


def _assert_within(base: Path, dest: Path) -> None:
    """Refuse any destination that resolves outside ``base`` (path traversal guard)."""
    if base != dest and base not in dest.parents:
        raise ValueError(f"refusing to write outside .claude: {dest}")


def _extract_frontmatter_and_body(content: str) -> tuple[str | None, str]:
    """Split a Claude command ``.md`` into (frontmatter, body); mirrors install.js."""
    if not content.startswith("---"):
        return None, content
    end = content.find("---", 3)
    if end == -1:
        return None, content
    return content[3:end].strip(), content[end + 3 :]


def _frontmatter_field(frontmatter: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", frontmatter, re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().strip("'\"")


def _command_to_skill(content: str, skill_name: str) -> str:
    """Convert a GSD command ``.md`` into a Claude ``SKILL.md``.

    Faithful (minimal) port of get-shit-done-cc's ``convertClaudeCommandToClaudeSkill``:
    rebuild the frontmatter with the canonical hyphen name (``gsd-<cmd>``) so the skill
    loader and tab-autocomplete use the command namespace, preserving description,
    argument-hint, agent, and the allowed-tools YAML list. Body passes through.
    """
    frontmatter, body = _extract_frontmatter_and_body(content)
    if frontmatter is None:
        return content

    description = _frontmatter_field(frontmatter, "description") or ""
    argument_hint = _frontmatter_field(frontmatter, "argument-hint")
    agent = _frontmatter_field(frontmatter, "agent")

    tools_match = re.search(r"^allowed-tools:\s*\n((?:\s+-\s+.+\n?)*)", frontmatter, re.MULTILINE)
    tools_block = ""
    if tools_match:
        tools_block = "allowed-tools:\n" + tools_match.group(1)
        if not tools_block.endswith("\n"):
            tools_block += "\n"

    fm = f"---\nname: {skill_name}\ndescription: {json.dumps(description)}\n"
    if argument_hint:
        fm += f"argument-hint: {json.dumps(argument_hint)}\n"
    if agent:
        fm += f"agent: {agent}\n"
    if tools_block:
        fm += tools_block
    fm += "---"
    return f"{fm}\n{body}"


def _apply_path_prefix(content: str, path_prefix: str) -> str:
    """Rewrite global runtime references to the project-local ``.claude/`` runtime.

    Mirrors install.js's local-install path replacement: ``$HOME/.claude/`` and
    ``~/.claude/`` point at the installed ``get-shit-done`` runtime; ``./.claude/``
    is already project-local and left untouched.
    """
    return content.replace("~/.claude/", path_prefix).replace("$HOME/.claude/", path_prefix)


def install_gsd(
    root: Path,
    *,
    dry_run: bool = False,
    state: FlowStateModel | None = None,
) -> list[Path]:
    """Lay down the full vendored GSD distribution into ``root/.claude/``.

    UNCONDITIONAL: no detection, no prompt. Copies the ``get-shit-done`` runtime and
    the full ``node_modules`` (so ``gsd-sdk`` is directly invokable via ``node``), and
    converts each ``commands/gsd/*.md`` into a ``.claude/skills/gsd-<cmd>/SKILL.md``.
    Idempotent, path-safe, dry-run-safe, manifest-tracked. Returns the GSD tree dests
    (the paths that WOULD be written when ``dry_run`` is True).
    """
    source = _vendor_gsd_source()
    claude_root = (root / ".claude").resolve()
    installed: list[Path] = []
    if not source.is_dir():
        return installed

    # Local-install path prefix: skills reference the project-local runtime.
    path_prefix = f"{claude_root}/"

    # 1 + 2: whole-tree copies (runtime, then node_modules for gsd-sdk resolution).
    for src_subpath, dest_relpath in _GSD_TREE_MAPPINGS:
        src_dir = source / src_subpath
        dest_dir = (claude_root / dest_relpath).resolve()
        _assert_within(claude_root, dest_dir)
        if not src_dir.is_dir():
            continue
        installed.append(dest_dir)
        if dry_run:
            continue
        _copy_tree(src_dir, dest_dir)
        if state is not None:
            _register(state, f".claude/{dest_relpath}", owner="gsd")

    # 3: per-command skill conversion into .claude/skills/gsd-<cmd>/SKILL.md.
    commands_dir = source / _GSD_PKG / "commands" / "gsd"
    skills_root = (claude_root / "skills").resolve()
    if commands_dir.is_dir():
        for md in sorted(commands_dir.glob("*.md")):
            skill_name = f"gsd-{md.stem}"
            dest_dir = (skills_root / skill_name).resolve()
            _assert_within(claude_root, dest_dir)
            if dry_run:
                continue
            content = _apply_path_prefix(md.read_text(encoding="utf-8"), path_prefix)
            skill_md = _command_to_skill(content, skill_name)
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
            if state is not None:
                _register(state, f".claude/skills/{skill_name}", owner="gsd")

    return installed


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

    # Phase 15: also lay down the vendored GSD distribution, unconditionally.
    installed.extend(install_gsd(root, dry_run=dry_run, state=state))

    return installed
