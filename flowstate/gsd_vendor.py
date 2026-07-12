"""GSD vendor service — inspect the pinned GSD snapshot and refresh it deliberately.

This module is the **executable form** of ``flowstate/vendor/VENDORING.md``: it encodes
the ONE canonical lean-npm-install procedure that 15-01 used, so the committed snapshot and
any later refresh can never diverge. It mirrors ``flowstate/pack.py``'s shape — a binary
locator, a result dataclass, and public functions — and mirrors ``is_pack_stale``'s
read-only provenance approach.

Guarantees (threat register T-15-10 / T-15-11 / T-15-12):

- **No silent drift** — inspection (``read_vendored_version`` / ``gsd_provenance``) never
  mutates the vendored tree. Only an explicit ``refresh(version)`` call rewrites it.
- **Pinned-only** — ``refresh`` refuses moving/floating tags (``latest``, ranges); an exact
  semver is required and captured in the lockfile.
- **Lean re-install** — refresh re-excludes the optional platform binary and fails if any
  vendored file exceeds 10M, then verifies ``gsd-sdk`` parity before overwriting the tree.
- **No new Python dependency**; no vendored GSD code is executed except the read-only
  ``gsd-sdk`` parity check.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import flowstate
from flowstate.sandbox import wrap

# Canonical constants — single source of truth shared with VENDORING.md / 15-01.
NPM_PACKAGE = "get-shit-done-cc"
PINNED_VERSION = "1.42.3"
MAX_FILE_BYTES = 10 * 1024 * 1024  # matches the check-added-large-files hook exclusion rationale
_PLATFORM_BINARY_GLOB = "@anthropic-ai/claude-agent-sdk-*"
_PARITY_PHASE = 15
_PARITY_EXPECT = "Bundle GSD"

# An exact, pinned semver: MAJOR.MINOR.PATCH with an optional prerelease/build suffix.
# Deliberately rejects ranges (^ ~ >= x), partial versions (1.42), and dist-tags (latest).
_PINNED_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _find_npm() -> str:
    """Locate the npm CLI binary (mirrors flowstate.pack._find_repomix).

    Resolution order: ``FLOWSTATE_NPM_BIN`` env var -> ``shutil.which("npm")`` -> "".
    """
    env_path = os.environ.get("FLOWSTATE_NPM_BIN")
    if env_path and Path(env_path).is_file():
        return env_path
    return shutil.which("npm") or ""


def _find_node() -> str:
    """Locate the node runtime used only for the read-only gsd-sdk parity check."""
    env_path = os.environ.get("FLOWSTATE_NODE_BIN")
    if env_path and Path(env_path).is_file():
        return env_path
    return shutil.which("node") or ""


def _default_vendor_dir() -> Path:
    """The vendored GSD distribution shipped inside the package (mirrors installer)."""
    return Path(flowstate.__file__).parent / "vendor" / "gsd"


def _is_pinned_version(version: str) -> bool:
    """Return True only for an exact pinned semver; reject moving tags and ranges."""
    return bool(_PINNED_RE.match(version or ""))


@dataclass
class VendoredVersion:
    """Parsed provenance from ``flowstate/vendor/gsd/VERSION`` (inspectable, read-only)."""

    package: str
    npm_version: str
    lockfile: str
    integrity: str | None = None
    resolved: str | None = None
    license: str | None = None
    install_command: str | None = None
    raw: str = ""


@dataclass
class RefreshResult:
    """Result of a deliberate refresh() invocation (mirrors flowstate.pack.PackResult)."""

    success: bool
    version: str | None = None
    vendored_path: Path | None = None
    exit_code: int = 0
    error: str | None = None


def _parse_version_file(text: str) -> dict[str, str]:
    """Parse ``key:   value`` lines from a VERSION file, ignoring comments/blanks."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if sep and not key.startswith(" "):
            fields[key.strip()] = value.strip()
    return fields


def read_vendored_version(vendor_dir: Path | None = None) -> VendoredVersion:
    """Read the pinned npm version + lockfile reference from ``<vendor_dir>/VERSION``.

    Args:
        vendor_dir: The vendored GSD dir. Defaults to the shipped ``flowstate/vendor/gsd``.

    Returns:
        VendoredVersion with the npm version, lockfile reference, and integrity string.

    Raises:
        FileNotFoundError: if the VERSION file is absent.
    """
    vendor_dir = vendor_dir or _default_vendor_dir()
    version_path = vendor_dir / "VERSION"
    if not version_path.is_file():
        raise FileNotFoundError(f"vendored GSD VERSION not found: {version_path}")

    raw = version_path.read_text()
    fields = _parse_version_file(raw)
    return VendoredVersion(
        package=fields.get("package", ""),
        npm_version=fields.get("npm_version", ""),
        lockfile=fields.get("lockfile", ""),
        integrity=fields.get("integrity"),
        resolved=fields.get("resolved"),
        license=fields.get("license"),
        install_command=fields.get("install_command"),
        raw=raw,
    )


def _oversize_files(node_modules: Path) -> list[str]:
    """Return relative paths of any file exceeding MAX_FILE_BYTES (read-only)."""
    oversize: list[str] = []
    if not node_modules.is_dir():
        return oversize
    for p in node_modules.rglob("*"):
        if p.is_file() and not p.is_symlink() and p.stat().st_size > MAX_FILE_BYTES:
            oversize.append(str(p.relative_to(node_modules)))
    return oversize


def _platform_binary_dirs(node_modules: Path) -> list[Path]:
    """Return any optional platform binary dirs present under node_modules."""
    if not node_modules.is_dir():
        return []
    return [p for p in node_modules.glob(_PLATFORM_BINARY_GLOB) if p.is_dir()]


def gsd_provenance(vendor_dir: Path | None = None) -> dict:
    """Report the currently pinned GSD provenance without mutating anything.

    Mirrors ``flowstate.pack.is_pack_stale``'s read-only, on-disk approach: no network,
    no writes. Surfaces the pin, lockfile, and whether the lean-install invariants
    (platform binary excluded, no file >10M) still hold for the committed snapshot.
    """
    vendor_dir = vendor_dir or _default_vendor_dir()
    node_modules = vendor_dir / "node_modules"
    lockfile_path = vendor_dir / "package-lock.json"

    try:
        version = read_vendored_version(vendor_dir)
        npm_version = version.npm_version
        install_command = version.install_command
        lockfile_ref = version.lockfile
    except FileNotFoundError:
        npm_version = ""
        install_command = None
        lockfile_ref = ""

    oversize = _oversize_files(node_modules)
    platform_dirs = _platform_binary_dirs(node_modules)

    return {
        "package": NPM_PACKAGE,
        "npm_version": npm_version,
        "lockfile": lockfile_ref,
        "lockfile_present": lockfile_path.is_file(),
        "tree_present": (node_modules / NPM_PACKAGE).is_dir(),
        "platform_binary_excluded": not platform_dirs,
        "oversize_files": oversize,
        "install_command": install_command,
        "vendor_dir": str(vendor_dir),
    }


def _write_version_file(
    vendor_dir: Path, version: str, lockfile_ref: str, integrity: str | None, resolved: str | None
) -> None:
    """Rewrite ``<vendor_dir>/VERSION`` for the refreshed pin (single source of truth)."""
    lines = [
        "# Vendored GSD — provenance",
        "",
        f"package:          {NPM_PACKAGE}",
        f"npm_version:      {version}",
    ]
    if resolved:
        lines.append(f"resolved:         {resolved}")
    if integrity:
        lines.append(f"integrity:        {integrity}")
    lines += [
        "license:          MIT (© 2025 Lex Christopherson) — see ./LICENSE (verbatim)",
        f"gsd_sdk_version:  {version} (node bin/gsd-sdk.js --version)",
        "",
        "# Reproducible dependency set",
        f"lockfile:         {lockfile_ref}",
        f"install_command:  npm install {NPM_PACKAGE}@{version} --omit=optional --omit=dev",
        "platform_binary:  EXCLUDED — the optional @anthropic-ai/claude-agent-sdk-<platform>",
        "                  binary is deliberately NOT vendored (--omit=optional).",
        "",
        "# See ../VENDORING.md for the canonical, reproducible vendoring procedure.",
        "",
    ]
    (vendor_dir / "VERSION").write_text("\n".join(lines))


def _lockfile_provenance(lockfile_path: Path) -> tuple[str | None, str | None]:
    """Best-effort extract (resolved, integrity) for get-shit-done-cc from a lockfile."""
    if not lockfile_path.is_file():
        return None, None
    import json

    try:
        data = json.loads(lockfile_path.read_text())
    except (ValueError, OSError):
        return None, None
    packages = data.get("packages", {})
    entry = packages.get(f"node_modules/{NPM_PACKAGE}", {})
    return entry.get("resolved"), entry.get("integrity")


def refresh(
    version: str,
    *,
    vendor_dir: Path | None = None,
    npm_bin: str | None = None,
    node_bin: str | None = None,
    scratch_dir: Path | None = None,
    parity_phase: int = _PARITY_PHASE,
    parity_expect: str = _PARITY_EXPECT,
    parity_cwd: Path | None = None,
    timeout: int = 600,
) -> RefreshResult:
    """Deliberately re-vendor the pinned GSD snapshot using the canonical procedure.

    This is the ONLY function that mutates the vendored tree, and it does so only when
    invoked explicitly with a pinned semver. It performs the exact steps documented in
    ``flowstate/vendor/VENDORING.md``:

    1. Refuse a moving/floating tag — require an exact pinned semver.
    2. ``npm install {NPM_PACKAGE}@<version> --omit=optional --omit=dev`` into a clean
       scratch dir (never the repo tree).
    3. Re-exclude the optional platform binary dir and FAIL if any file exceeds 10M.
    4. Verify ``gsd-sdk`` parity by running ``node .../bin/gsd-sdk.js query
       roadmap.get-phase <N>`` and asserting the expected phase name appears.
    5. Only then overwrite ``<vendor_dir>/node_modules`` + lockfile + LICENSE + VERSION.

    Any failure leaves the committed snapshot untouched.
    """
    if not _is_pinned_version(version):
        return RefreshResult(
            success=False,
            version=version,
            exit_code=2,
            error=(
                f"refusing to refresh to '{version}': a pinned exact semver is required "
                "(moving tags like 'latest' and ranges like '^1.2.3' are refused)."
            ),
        )

    vendor_dir = vendor_dir or _default_vendor_dir()
    npm_bin = npm_bin or _find_npm()
    if not npm_bin:
        return RefreshResult(
            success=False,
            version=version,
            exit_code=1,
            error="npm CLI not found. Install Node/npm or set FLOWSTATE_NPM_BIN.",
        )

    node_bin = node_bin or _find_node()
    if not node_bin:
        return RefreshResult(
            success=False,
            version=version,
            exit_code=1,
            error="node not found (required for the gsd-sdk parity check). Set FLOWSTATE_NODE_BIN.",
        )

    # Use a caller-provided scratch dir (tests) or a private temp dir; never the repo tree.
    tmp_ctx: tempfile.TemporaryDirectory | None = None
    if scratch_dir is None:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="gsd-vendor-")
        scratch = Path(tmp_ctx.name)
    else:
        scratch = scratch_dir
        scratch.mkdir(parents=True, exist_ok=True)

    try:
        (scratch / "package.json").write_text(
            '{"name":"gsd-vendor-scratch","version":"1.0.0","private":true}\n'
        )
        cmd = [
            npm_bin,
            "install",
            f"{NPM_PACKAGE}@{version}",
            "--omit=optional",
            "--omit=dev",
            "--no-audit",
            "--no-fund",
        ]
        try:
            # SBX-03/D-02: default observe tier — refresh() is NOT project-scoped
            # (its only caller, `gsd_version --refresh`, has no `root`/resolve_root()
            # call), so no ProjectPreferences.sandbox is threaded here; Path.cwd() is
            # the correct placeholder since observe ignores project_root.
            #
            # WR-2 (25-CONTEXT.md D-04, documented not fixed): observe's denylist
            # strips any `*_TOKEN`-suffixed var, including `NPM_TOKEN`. A private
            # registry `.npmrc` using `//registry/:_authToken=${NPM_TOKEN}` would
            # fail here with a 401/403 that looks like npm rejecting auth, not a
            # scrubbed-env signal. This is FlowState's public-`get-shit-done-cc`-
            # from-public-npm path, so it's accepted as-is; a private-registry
            # user must point FLOWSTATE_NPM_BIN at a pre-authenticated npm config
            # rather than relying on an env var this scrub deliberately removes.
            cmd, env = wrap(cmd, "tool", Path.cwd(), {**os.environ})
            proc = subprocess.run(
                cmd, cwd=scratch, capture_output=True, text=True, timeout=timeout, env=env
            )
        except subprocess.TimeoutExpired:
            return RefreshResult(
                success=False,
                version=version,
                exit_code=-1,
                error=f"npm install timed out after {timeout}s",
            )
        if proc.returncode != 0:
            return RefreshResult(
                success=False,
                version=version,
                exit_code=proc.returncode,
                error=proc.stderr or f"npm install exited {proc.returncode}",
            )

        node_modules = scratch / "node_modules"
        pkg_dir = node_modules / NPM_PACKAGE
        if not pkg_dir.is_dir():
            return RefreshResult(
                success=False,
                version=version,
                exit_code=1,
                error=f"npm install produced no {NPM_PACKAGE} tree under node_modules/",
            )

        # Step 3: re-exclude platform binary, then enforce the 10M ceiling.
        for plat in _platform_binary_dirs(node_modules):
            shutil.rmtree(plat, ignore_errors=True)
        oversize = _oversize_files(node_modules)
        if oversize:
            return RefreshResult(
                success=False,
                version=version,
                exit_code=1,
                error=(
                    "refusing to vendor: file(s) exceed the 10M large-file ceiling: "
                    + ", ".join(oversize[:5])
                ),
            )

        # Step 4: read-only gsd-sdk parity gate (the only vendored code we ever run).
        gsd_sdk = pkg_dir / "bin" / "gsd-sdk.js"
        if not gsd_sdk.is_file():
            return RefreshResult(
                success=False,
                version=version,
                exit_code=1,
                error=f"gsd-sdk.js missing from freshly installed {NPM_PACKAGE}",
            )
        try:
            # SBX-03/D-02: default observe tier — same rationale as the npm install
            # site above; refresh() is not project-scoped.
            #
            # WR-2 (25-CONTEXT.md D-04, documented not fixed): same NPM_TOKEN /
            # *_TOKEN scrub limitation as the npm install site above applies
            # here too — see that comment for the full rationale.
            parity_cmd, parity_env = wrap(
                [node_bin, str(gsd_sdk), "query", "roadmap.get-phase", str(parity_phase)],
                "tool",
                Path.cwd(),
                {**os.environ},
            )
            parity = subprocess.run(
                parity_cmd,
                cwd=str(parity_cwd or Path.cwd()),
                capture_output=True,
                text=True,
                timeout=60,
                env=parity_env,
            )
        except subprocess.TimeoutExpired:
            return RefreshResult(
                success=False,
                version=version,
                exit_code=-1,
                error="gsd-sdk parity check timed out",
            )
        if parity_expect not in parity.stdout:
            return RefreshResult(
                success=False,
                version=version,
                exit_code=parity.returncode or 1,
                error=(
                    f"gsd-sdk parity check failed: expected '{parity_expect}' in output "
                    f"of `roadmap.get-phase {parity_phase}` (got: {parity.stdout[:120]!r})"
                ),
            )

        # Step 5: overwrite the committed snapshot atomically-ish (dest is fully rebuilt).
        lockfile_src = scratch / "package-lock.json"
        resolved, integrity = _lockfile_provenance(lockfile_src)

        vendor_dir.mkdir(parents=True, exist_ok=True)
        dest_modules = vendor_dir / "node_modules"
        if dest_modules.exists():
            shutil.rmtree(dest_modules)
        shutil.copytree(node_modules, dest_modules)
        if lockfile_src.is_file():
            shutil.copy2(lockfile_src, vendor_dir / "package-lock.json")
        license_src = pkg_dir / "LICENSE"
        if license_src.is_file():
            shutil.copy2(license_src, vendor_dir / "LICENSE")

        _write_version_file(
            vendor_dir, version, "./package-lock.json (lockfileVersion 3)", integrity, resolved
        )

        return RefreshResult(success=True, version=version, vendored_path=vendor_dir, exit_code=0)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
