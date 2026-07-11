"""Tests for flowstate.gsd_vendor — pinned GSD version inspection, provenance, deliberate refresh.

All tests are OFFLINE: no live ``npm install`` and no network. The refresh path is
exercised with fake ``npm``/``node`` shell scripts so the canonical lean-install
procedure is verified without fetching anything. The default inspection path never
mutates the vendored tree (threat T-15-10: no silent snapshot drift).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from flowstate.gsd_vendor import (
    NPM_PACKAGE,
    PINNED_VERSION,
    RefreshResult,
    _find_npm,
    _is_pinned_version,
    gsd_provenance,
    read_vendored_version,
    refresh,
)

# The real vendored tree shipped in the package (source of truth from 15-01).
_REAL_VENDOR = Path(__file__).resolve().parent.parent / "flowstate" / "vendor" / "gsd"


# ---------------------------------------------------------------------------
# Helpers — build a minimal fake vendor dir so tests never touch the real tree
# ---------------------------------------------------------------------------


def _make_fake_vendor(root: Path, *, version: str = "1.42.3") -> Path:
    """Create a minimal fake flowstate/vendor/gsd/ with VERSION + lockfile + tree."""
    vendor = root / "gsd"
    (vendor / "node_modules" / "get-shit-done-cc" / "bin").mkdir(parents=True)
    (vendor / "node_modules" / "get-shit-done-cc" / "bin" / "gsd-sdk.js").write_text(
        "// fake gsd-sdk\n"
    )
    (vendor / "node_modules" / "get-shit-done-cc" / "LICENSE").write_text("MIT\n")
    (vendor / "package-lock.json").write_text('{"lockfileVersion": 3, "packages": {}}\n')
    (vendor / "LICENSE").write_text("MIT\n")
    (vendor / "VERSION").write_text(
        "# Vendored GSD — provenance\n"
        "\n"
        f"package:          {NPM_PACKAGE}\n"
        f"npm_version:      {version}\n"
        f"resolved:         https://registry.npmjs.org/{NPM_PACKAGE}/-/x-{version}.tgz\n"
        "integrity:        sha512-DEADBEEF==\n"
        "license:          MIT (© 2025 Lex Christopherson)\n"
        "\n"
        "lockfile:         ./package-lock.json (lockfileVersion 3)\n"
        f"install_command:  npm install {NPM_PACKAGE}@{version} --omit=optional --omit=dev\n"
    )
    return vendor


def _write_fake_npm(bin_dir: Path) -> Path:
    """Fake npm that lays down a lean node_modules + package-lock.json into cwd."""
    npm = bin_dir / "npm"
    npm.write_text(
        "#!/bin/sh\n"
        "# Fake npm: create a lean node_modules tree in the cwd.\n"
        "PKGDIR=node_modules/get-shit-done-cc\n"
        'mkdir -p "$PKGDIR/bin"\n'
        'echo "// gsd-sdk" > "$PKGDIR/bin/gsd-sdk.js"\n'
        'echo "MIT" > "$PKGDIR/LICENSE"\n'
        'echo \'{"lockfileVersion": 3, "packages": {}}\' > package-lock.json\n'
        "exit 0\n"
    )
    npm.chmod(0o755)
    return npm


def _write_fake_node(bin_dir: Path, *, parity_text: str = "Bundle GSD") -> Path:
    """Fake node that prints the expected gsd-sdk parity output."""
    node = bin_dir / "node"
    node.write_text(f'#!/bin/sh\necho \'{{"phase_name": "{parity_text}"}}\'\nexit 0\n')
    node.chmod(0o755)
    return node


# ---------------------------------------------------------------------------
# TestFindNpm
# ---------------------------------------------------------------------------


class TestFindNpm:
    def test_env_override_returns_path_when_file_exists(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "npm-custom"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_NPM_BIN", str(fake))
        assert _find_npm() == str(fake)

    def test_which_detection(self, tmp_path: Path, monkeypatch):
        fake = tmp_path / "npm"
        fake.write_text("#!/bin/sh\necho ok")
        fake.chmod(0o755)
        monkeypatch.delenv("FLOWSTATE_NPM_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))
        assert _find_npm() == str(fake)

    def test_missing_returns_empty_string(self, monkeypatch):
        monkeypatch.delenv("FLOWSTATE_NPM_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        assert _find_npm() == ""


# ---------------------------------------------------------------------------
# TestIsPinnedVersion — floating/moving tags must be refused
# ---------------------------------------------------------------------------


class TestIsPinnedVersion:
    def test_exact_semver_is_pinned(self):
        assert _is_pinned_version("1.42.3") is True

    def test_moving_tags_rejected(self):
        for tag in ("latest", "next", "beta", "canary", "*", ""):
            assert _is_pinned_version(tag) is False, tag

    def test_ranges_rejected(self):
        for spec in ("^1.42.3", "~1.42.3", ">=1.0.0", "1.x", "1.42"):
            assert _is_pinned_version(spec) is False, spec

    def test_prerelease_semver_is_pinned(self):
        assert _is_pinned_version("2.0.0-rc.1") is True


# ---------------------------------------------------------------------------
# TestReadVendoredVersion — inspectable provenance from the real shipped tree
# ---------------------------------------------------------------------------


class TestReadVendoredVersion:
    def test_reads_real_shipped_version(self):
        """The real vendored VERSION (written by 15-01) is inspectable."""
        v = read_vendored_version()
        assert v.package == NPM_PACKAGE
        assert v.npm_version == PINNED_VERSION
        assert v.lockfile  # lockfile reference present
        assert v.integrity  # integrity captured for reproducibility

    def test_reads_from_explicit_vendor_dir(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path, version="9.9.9")
        v = read_vendored_version(vendor)
        assert v.npm_version == "9.9.9"
        assert v.package == NPM_PACKAGE

    def test_missing_version_file_raises(self, tmp_path: Path):
        try:
            read_vendored_version(tmp_path / "nonexistent")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("expected FileNotFoundError")


# ---------------------------------------------------------------------------
# TestProvenance — read-only report mirroring is_pack_stale (no mutation, no net)
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_real_tree_provenance(self):
        prov = gsd_provenance()
        assert prov["npm_version"] == PINNED_VERSION
        assert prov["tree_present"] is True
        assert prov["platform_binary_excluded"] is True
        assert prov["oversize_files"] == []  # 15-01 excluded the 197M binary

    def test_provenance_does_not_mutate_tree(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        before = sorted(p.name for p in vendor.rglob("*"))
        gsd_provenance(vendor)
        after = sorted(p.name for p in vendor.rglob("*"))
        assert before == after

    def test_provenance_flags_oversize_file(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        big = vendor / "node_modules" / "get-shit-done-cc" / "big.bin"
        big.write_bytes(b"\0" * (11 * 1024 * 1024))
        prov = gsd_provenance(vendor)
        assert prov["oversize_files"] != []

    def test_provenance_flags_platform_binary(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        plat = vendor / "node_modules" / "@anthropic-ai" / "claude-agent-sdk-darwin-arm64"
        plat.mkdir(parents=True)
        (plat / "claude").write_text("binary\n")
        prov = gsd_provenance(vendor)
        assert prov["platform_binary_excluded"] is False


# ---------------------------------------------------------------------------
# TestRefreshGuards — deliberate-only, pinned-only, never a silent side effect
# ---------------------------------------------------------------------------


class TestRefreshGuards:
    def test_refresh_refuses_moving_tag(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        before = (vendor / "VERSION").read_text()
        result = refresh("latest", vendor_dir=vendor)
        assert isinstance(result, RefreshResult)
        assert result.success is False
        assert "pin" in result.error.lower() or "moving" in result.error.lower()
        # Refusal must NOT rewrite the tree.
        assert (vendor / "VERSION").read_text() == before

    def test_refresh_refuses_range(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        result = refresh("^1.42.3", vendor_dir=vendor)
        assert result.success is False

    def test_refresh_absent_npm_fails_without_mutation(self, tmp_path: Path, monkeypatch):
        vendor = _make_fake_vendor(tmp_path)
        before = (vendor / "VERSION").read_text()
        monkeypatch.delenv("FLOWSTATE_NPM_BIN", raising=False)
        monkeypatch.setenv("PATH", "")
        result = refresh("1.43.0", vendor_dir=vendor)
        assert result.success is False
        assert "npm" in result.error.lower()
        assert (vendor / "VERSION").read_text() == before


# ---------------------------------------------------------------------------
# TestRefreshProcedure — the canonical lean-install path with fake npm/node
# ---------------------------------------------------------------------------


class TestRefreshProcedure:
    def test_happy_path_rewrites_tree_and_version(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path, version="1.42.3")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npm = _write_fake_npm(bin_dir)
        node = _write_fake_node(bin_dir)
        scratch = tmp_path / "scratch"

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=scratch,
            parity_cwd=tmp_path,
        )
        assert result.success is True, result.error
        # VERSION rewritten to the new pin.
        v = read_vendored_version(vendor)
        assert v.npm_version == "1.43.0"
        # Vendored tree replaced with the freshly-installed lean tree.
        assert (vendor / "node_modules" / "get-shit-done-cc" / "bin" / "gsd-sdk.js").is_file()

    def test_refresh_fails_on_oversize_installed_file(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # Fake npm that installs an 11M file (simulates the platform binary sneaking in).
        npm = bin_dir / "npm"
        npm.write_text(
            "#!/bin/sh\n"
            "PKGDIR=node_modules/get-shit-done-cc\n"
            'mkdir -p "$PKGDIR/bin"\n'
            'echo "// gsd-sdk" > "$PKGDIR/bin/gsd-sdk.js"\n'
            'dd if=/dev/zero of="$PKGDIR/huge.bin" bs=1048576 count=11 2>/dev/null\n'
            "echo '{\"lockfileVersion\": 3}' > package-lock.json\n"
            "exit 0\n"
        )
        npm.chmod(0o755)
        node = _write_fake_node(bin_dir)
        before = (vendor / "VERSION").read_text()

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=tmp_path / "scratch",
            parity_cwd=tmp_path,
        )
        assert result.success is False
        assert "10m" in result.error.lower() or "large" in result.error.lower()
        # Failed refresh leaves the committed tree untouched.
        assert (vendor / "VERSION").read_text() == before

    def test_refresh_removes_platform_binary(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # Fake npm that installs the optional platform binary dir despite --omit.
        npm = bin_dir / "npm"
        npm.write_text(
            "#!/bin/sh\n"
            "PKGDIR=node_modules/get-shit-done-cc\n"
            'mkdir -p "$PKGDIR/bin"\n'
            'echo "// gsd-sdk" > "$PKGDIR/bin/gsd-sdk.js"\n'
            "PLAT=node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64\n"
            'mkdir -p "$PLAT"\n'
            'echo "small" > "$PLAT/claude"\n'
            "echo '{\"lockfileVersion\": 3}' > package-lock.json\n"
            "exit 0\n"
        )
        npm.chmod(0o755)
        node = _write_fake_node(bin_dir)

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=tmp_path / "scratch",
            parity_cwd=tmp_path,
        )
        assert result.success is True, result.error
        plat = vendor / "node_modules" / "@anthropic-ai" / "claude-agent-sdk-darwin-arm64"
        assert not plat.exists()

    def test_refresh_fails_when_parity_check_fails(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npm = _write_fake_npm(bin_dir)
        # Node prints the WRONG phase name → parity gate must fail.
        node = _write_fake_node(bin_dir, parity_text="Something Else")
        before = (vendor / "VERSION").read_text()

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=tmp_path / "scratch",
            parity_cwd=tmp_path,
        )
        assert result.success is False
        assert "parity" in result.error.lower()
        assert (vendor / "VERSION").read_text() == before

    def test_refresh_fails_when_install_produces_no_tree(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # npm exits 0 but installs nothing.
        npm = bin_dir / "npm"
        npm.write_text("#!/bin/sh\nexit 0\n")
        npm.chmod(0o755)
        node = _write_fake_node(bin_dir)

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=tmp_path / "scratch",
            parity_cwd=tmp_path,
        )
        assert result.success is False

    def test_refresh_fails_when_npm_errors(self, tmp_path: Path):
        vendor = _make_fake_vendor(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        npm = bin_dir / "npm"
        npm.write_text("#!/bin/sh\necho 'boom' >&2\nexit 1\n")
        npm.chmod(0o755)
        node = _write_fake_node(bin_dir)

        result = refresh(
            "1.43.0",
            vendor_dir=vendor,
            npm_bin=str(npm),
            node_bin=str(node),
            scratch_dir=tmp_path / "scratch",
            parity_cwd=tmp_path,
        )
        assert result.success is False


def test_real_vendor_dir_exists():
    """Sanity: the shipped vendor tree the CLI inspects is present."""
    assert (_REAL_VENDOR / "VERSION").is_file()
    assert shutil.which  # imported symbol used
