# Phase 23: Linux Parity + Core Seam - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 2 (both new)
**Analogs found:** 2 / 2 (composite — no single file matches; each new file draws from 2-3 analogs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog(s) | Match Quality |
|--------------------|------|-----------|--------------------|----------------|
| `flowstate/sandbox.py` | utility (transform + external-binary locator, hybrid) | transform (pure `(argv, env)` in/out) + file-I/O (subprocess exec for `confine` tier profile builders) | `flowstate/bridge.py` (env-scrub + subprocess pattern), `flowstate/pack.py` (binary locator + Result/Config dataclass shape), `flowstate/embeddings.py` (graceful-degradation module contract) | role-match (composite — no single existing file is both a locator and a pure transform) |
| `tests/test_sandbox.py` | test | transform (unit) + golden (string/list equality) | `tests/test_pack.py` (`TestFindRepomix` class-per-concept + monkeypatch env/PATH pattern), `tests/test_context_prefix.py` (`TestDeterminism` byte-identical assertion pattern), `tests/test_embeddings.py` (graceful-degradation-when-absent test pattern) | role-match |

**No file in the codebase is a request-response controller or CRUD service** — `sandbox.py` is architecturally closest to `pack.py`/`gsd_vendor.py` (external-binary-locator utilities) crossed with `embeddings.py` (optional/degrading pure-transform module). Both are cited below with concrete excerpts.

## Pattern Assignments

### `flowstate/sandbox.py` (utility, transform + file-I/O)

**Primary analog:** `flowstate/bridge.py` (env-scrub + subprocess call-site shape)
**Secondary analogs:** `flowstate/pack.py` (locator + dataclass shape), `flowstate/embeddings.py` (module docstring/graceful-degradation contract)

#### 1. Env-scrub transform — the exact model and future call site

**Source:** `flowstate/bridge.py:299-315`
```python
        # Unset CLAUDECODE env var to allow nested invocation
        env = {**os.environ}
        env.pop("CLAUDECODE", None)
        # Opt-in: raise cache TTL from 5 min to 1 h for eligible API-key accounts
        if self.config.enable_prompt_caching_1h:
            env["ENABLE_PROMPT_CACHING_1H"] = "1"

        try:
            start = time.monotonic()
            result = subprocess.run(
                cmd,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=env,
            )
```
This is D-04's literal integration target (Phase 24, not this phase): `sandbox.wrap()`'s `_scrub_env()` generalizes the `env = {**os.environ}; env.pop(...)` shape into a denylist-with-carve-out transform. `sandbox.py` does NOT call `subprocess.run` itself for the `observe` tier — it hands back `(cmd, env)` for the caller (future `bridge.py`) to pass through unchanged, per D-04.

#### 2. Binary locator pattern — `_find_repomix()` / `_find_npm()` is the template for `check_bwrap_available()`'s presence half

**Source:** `flowstate/pack.py:19-45`
```python
def _find_repomix() -> str:
    """Locate the repomix CLI binary.

    Resolution order:
    1. FLOWSTATE_REPOMIX_BIN env var (must point to an existing file)
    2. shutil.which("repomix") (PATH search)
    3. Common install locations for Node global packages
    """
    env_path = os.environ.get("FLOWSTATE_REPOMIX_BIN")
    if env_path and Path(env_path).is_file():
        return env_path

    found = shutil.which("repomix")
    if found:
        return found

    # Common install locations for Node global packages
    candidates = [
        Path.home() / ".local" / "share" / "pnpm" / "repomix",
        Path.home() / ".npm-global" / "bin" / "repomix",
        Path("/usr/local/bin/repomix"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)

    return ""
```
Same shape at `flowstate/gsd_vendor.py:46-54` (`_find_npm`) and `:57-62` (`_find_node`) — three independent copies of the identical `env var > shutil.which > fallback candidates` resolution order confirm this is the house convention. `sandbox.py` should follow it exactly for locating `bwrap`/`sandbox-exec`, but per RESEARCH.md Pattern 3 (and Anti-Pattern warning), presence alone (`shutil.which`) is NOT sufficient for `bwrap` — pair it with the functional smoke test:

**Source:** RESEARCH.md Pattern 3, sourced from `/Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx/agent-sbx:147-152`
```python
def check_bwrap_available() -> bool:
    if shutil.which("bwrap") is None:
        return False
    try:
        result = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--", "/bin/true"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
```

#### 3. Result/Config dataclass shape (if `sandbox.py` needs one — optional per D-04, since `wrap()` returns a plain tuple not a Result object)

**Source:** `flowstate/pack.py:48-72`
```python
@dataclass
class PackResult:
    """Result of a run_pack() invocation."""

    success: bool
    output_path: Path | None = None
    exit_code: int = 0
    error: str | None = None


@dataclass
class PackConfig:
    """Configuration for a repomix pack invocation."""

    repomix_bin: str | None = None
    project_root: Path = field(default_factory=Path.cwd)
    output_path: Path | None = None
    timeout: int = 300
    compress: bool = False

    def __post_init__(self):
        if self.repomix_bin is None:
            self.repomix_bin = _find_repomix()
```
D-04 explicitly rejects a Result-object return for `wrap()` itself (plain `(argv, env)` tuple, no exception path, never fails hard) — this pattern is NOT for `wrap()`'s return value. It's the template if the planner wants an internal `_BwrapProbeResult`-style dataclass for the degradation-ladder bookkeeping (kernel version detected, landlock available, bwrap functional, tier actually applied) — optional, Claude's Discretion per CONTEXT.md.

#### 4. Module docstring + graceful-degradation contract style

**Source:** `flowstate/embeddings.py:1-19`
```python
"""Optional lazy embedding provider backed by fastembed.

Exposes a graceful-degradation seam: importing this module NEVER requires
fastembed.  The embedder activates only when the ``[semantic]`` pip extra is
installed and an embed() call is made.  When absent every caller sees
``available() == False`` and gets ``[]`` from ``embed()``.

Public API::

    provider = get_embedder(root=Path("."))
    if provider.available():
        vectors = provider.embed(["some text"])
        print(f"dim={provider.dim}")
...
```
`sandbox.py`'s module docstring should follow this exact "state the degradation contract in the first paragraph, show the public API as a doctest-style block" shape — e.g. "importing this module NEVER requires bwrap/landlock to be present; `wrap()` degrades to `observe`-only when the platform tier is unavailable, never raises." The lazy-import pattern for the Linux-only ctypes path also mirrors `embeddings.py:112-124`'s try/except-around-import:

**Source:** `flowstate/embeddings.py:99-124`
```python
    def _ensure_model(self) -> bool:
        """Try to load the fastembed model exactly once; cache the result.

        Returns True if the model is ready (or an embed_fn was injected),
        False when fastembed is absent or fails to load.  Never raises.
        """
        if self._embed_fn is not None:
            return True
        if self._model is not None:
            return True
        if self._unavailable:
            return False

        try:
            # Lazy import — intentional: importing this module must succeed
            # even when fastembed is not installed.
            from fastembed import TextEmbedding as _TextEmbedding

            # Also make it accessible at the module level for monkeypatching.
            global TextEmbedding  # type: ignore[name-defined]
            TextEmbedding = _TextEmbedding

            self._model = _TextEmbedding(self.model_name)
        except Exception:
            self._unavailable = True
            return False

        return True
```
Apply the same shape to the Linux ctypes path: guard on `sys.platform.startswith("linux")` at import/call time, cache a `_landlock_unavailable: bool` sentinel after first failure, never raise out of the availability probe.

#### 5. Core `wrap()` seam pattern (RESEARCH.md's design target — not yet in repo, D-04-derived)

**Source:** RESEARCH.md "Code Examples" section, "D-04 seam shape, with the Pitfall-1 auth carve-out"
```python
_AUTH_EXEMPT = {
    "ANTHROPIC_API_KEY",       # Pitfall 1: FlowState's own claude auth, not a leaked secret
    "CLAUDE_CODE_OAUTH_TOKEN", # Pitfall 1: same
    "CLAUDE_CONFIG_DIR",       # relocates .credentials.json; not secret-shaped but auth-relevant
}

def wrap(
    cmd: list[str],
    surface: str,
    project_root: Path,
    env: dict[str, str],
    *,
    tier: str = "observe",
) -> tuple[list[str], dict[str, str]]:
    """Transform (cmd, env) for subprocess confinement. Never spawns a process."""
    scrubbed_env = _scrub_env(env)  # D-01 denylist minus _AUTH_EXEMPT, always applied
    if tier == "observe":
        return cmd, scrubbed_env
    # tier == "confine" — platform dispatch, profile builders below
    if sys.platform == "darwin":
        return _wrap_macos(cmd, project_root, scrubbed_env)
    if sys.platform.startswith("linux"):
        return _wrap_linux(cmd, project_root, scrubbed_env)
    return cmd, scrubbed_env  # unsupported platform: env-scrub only, never hard-fail
```
This is the load-bearing signature the plan must implement verbatim per D-04. This is the seam itself, not an "analog" from elsewhere in the codebase — flagged here because it's the one piece of "code to copy from" that isn't a pre-existing file.

**Error handling pattern:** None needed for `observe` (pure dict transform, cannot fail). For `confine`'s profile-builder path, follow `bridge.py`'s narrow-exception-catch house style (`except subprocess.TimeoutExpired` / `except FileNotFoundError`, not bare `except Exception`) EXCEPT where RESEARCH.md's Anti-Patterns section explicitly overrides it: "catch `OSError` broadly (or check `errno`) for denied-write detection, not narrowly `PermissionError`" — this is a locked exception to the codebase's usual narrow-catch convention, call it out in the plan.

---

### `tests/test_sandbox.py` (test, transform + golden)

**Primary analog:** `tests/test_pack.py` (`TestFindRepomix` class structure + env/PATH monkeypatch pattern)
**Secondary analogs:** `tests/test_context_prefix.py` (`TestDeterminism` golden/byte-identical pattern), `tests/test_embeddings.py` (graceful-degradation-when-absent pattern), `tests/test_bridge.py` (fake-binary-via-`tmp_path` pattern)

#### 1. Class-per-concept + env/PATH monkeypatch — the template for locator tests (`check_bwrap_available`, platform dispatch)

**Source:** `tests/test_pack.py:1-80`
```python
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
    ...
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
```
Directly reusable for a `TestCheckBwrapAvailable` class: write a fake `bwrap` shell script to `tmp_path`, set `PATH`/`FLOWSTATE_BWRAP_BIN`-style env, assert the boolean outcome. Also reuse `test_pack.py:122-166`'s "write a script that records its argv to a file, then assert flag presence in the captured argv" pattern for asserting `_wrap_linux()`'s constructed `bwrap ...` argv contains expected flags — this is the closest existing precedent for argv-shape assertions without actually spawning the real sandboxed process.

#### 2. Byte-identical / golden-test pattern — the template for profile-builder golden tests (SBX-02's explicit requirement)

**Source:** `tests/test_context_prefix.py:376-389`
```python
class TestDeterminism:
    def test_identical_inputs_produce_identical_output(self, tmp_path: Path):
        """Two calls with the same inputs return byte-identical strings."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>deterministic</pack>")
        memory = _make_memory_stub("## Prior Knowledge\n\nfact\n")

        with patch("flowstate.context_prefix.run_pack"):
            result1 = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)
            result2 = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert result1 == result2, (
            "Two calls with identical inputs must produce byte-identical output"
        )
```
For `build_macos_profile()`/`build_linux_bwrap_args()`: write `TestBuildMacosProfile`/`TestBuildLinuxBwrapArgs` classes asserting exact string/list equality against a fixed fixture (not just "two calls match each other" — assert against a literal expected string, since these are pure I/O-free builders per RESEARCH.md Pattern 1). Example target shape from RESEARCH.md:
```python
def test_build_macos_profile_matches_spike_proven_shape(tmp_path):
    profile = build_macos_profile(tmp_path)
    assert profile == (
        "(version 1)\n"
        "(allow default)\n"
        "(deny file-write*)\n"
        f'(allow file-write*\n  (subpath "{tmp_path}")\n'
        '  (subpath "/private/tmp")\n'
        '  (subpath "/private/var/folders")\n'
        '  (subpath "/dev"))\n'
        f'(deny file-read* (subpath "{Path.home() / ".ssh"}"))\n'
    )
```

#### 3. Graceful-degradation-when-absent test pattern (for `observe` tier default, Linux-tier fallback ladder)

**Source:** `tests/test_embeddings.py` (test names, lines 36-108)
```python
def test_import_succeeds_without_fastembed(monkeypatch):
def test_available_returns_false_when_fastembed_absent(monkeypatch):
def test_embed_returns_empty_list_when_fastembed_absent(monkeypatch):
def test_available_returns_true_with_injected_embed_fn():
```
Mirror this naming/structure for sandbox degradation: `test_wrap_never_raises_when_bwrap_absent`, `test_wrap_degrades_to_observe_when_landlock_unavailable`, `test_confine_tier_falls_back_to_bwrap_only_below_kernel_5_13` (per D-02/D-03's ladder) — each asserting a graceful fallback value, never an exception.

#### 4. Fake-binary-via-`tmp_path` pattern (for `wrap()` integration-shape tests without real sandboxing)

**Source:** `tests/test_bridge.py:1-29`
```python
"""Tests for the ClaudeBridge."""

from pathlib import Path

from flowstate.bridge import CANON, BridgeConfig, BridgeUsage, ClaudeBridge, _find_claude


def test_dry_run_returns_success():
    bridge = ClaudeBridge(dry_run=True)
    result = bridge.run("Hello world")
    assert result.success
    assert "[dry-run]" in result.output


def test_available_when_claude_found(tmp_path: Path):
    fake_claude = tmp_path / "claude"
    fake_claude.write_text("#!/bin/sh\necho ok")
    fake_claude.chmod(0o755)

    config = BridgeConfig(claude_bin=str(fake_claude))
    bridge = ClaudeBridge(config=config)
    assert bridge.available
```
Use for the RESEARCH.md Pattern-2-mandated `observe`-tier test — note that pattern is even simpler (no fake binary at all, since `observe` never touches subprocess):
```python
def test_observe_scrubs_known_secret_patterns():
    argv = ["echo", "hi"]
    env = {
        "PATH": "/usr/bin",
        "AWS_SECRET_ACCESS_KEY": "leak-me-not",
        "HOME": "/home/x",
        "ANTHROPIC_API_KEY": "sk-ant-should-survive",   # Pitfall 1 carve-out
        "CLAUDE_CODE_OAUTH_TOKEN": "should-also-survive",  # Pitfall 1 carve-out
    }
    new_argv, new_env = wrap(argv, surface="llm", project_root=Path("/tmp/proj"), env=env)
    assert new_argv == argv                                # observe never touches argv
    assert "AWS_SECRET_ACCESS_KEY" not in new_env          # denylist match stripped
    assert new_env["ANTHROPIC_API_KEY"] == "sk-ant-should-survive"      # carve-out honored
    assert new_env["CLAUDE_CODE_OAUTH_TOKEN"] == "should-also-survive"  # carve-out honored
    assert new_env["PATH"] == "/usr/bin"                    # everything else passes through
    # No subprocess.run anywhere in this test.
```
(Source: RESEARCH.md Architecture Patterns, Pattern 2 — cited here because it's the canonical named regression test SBX-02 requires: `test_observe_never_strips_claude_auth_vars`.)

**Coverage note (from RESEARCH.md Project Constraints):** the Linux-only ctypes branches need `sys.platform` guards or `# pragma: no cover` markers so they don't tank the 80% coverage gate when tests run on this (Darwin) dev machine — consistent with `tests/conftest.py`'s existing `@pytest.mark.slow`/`@pytest.mark.integration` marker convention. Check `tests/conftest.py` for the exact marker registration before adding a new one (e.g. `@pytest.mark.linux_only`).

---

## Shared Patterns

### External-binary locator (env var > `shutil.which` > fallback candidates)
**Source:** `flowstate/pack.py:19-45`, duplicated at `flowstate/gsd_vendor.py:46-62`
**Apply to:** `sandbox.py`'s `bwrap`/`sandbox-exec` locators. Naming convention: `FLOWSTATE_BWRAP_BIN` / `FLOWSTATE_SANDBOX_EXEC_BIN`, matching the `FLOWSTATE_<TOOL>_BIN` env-var naming already used for `FLOWSTATE_CLAUDE_BIN`, `FLOWSTATE_REPOMIX_BIN`, `FLOWSTATE_NPM_BIN`, `FLOWSTATE_NODE_BIN`.

### Env dict transform (`{**os.environ}` + selective pop/set)
**Source:** `flowstate/bridge.py:300-304`
```python
env = {**os.environ}
env.pop("CLAUDECODE", None)
if self.config.enable_prompt_caching_1h:
    env["ENABLE_PROMPT_CACHING_1H"] = "1"
```
**Apply to:** `sandbox._scrub_env()` — same shallow-copy-then-mutate shape, generalized to a denylist loop with the `_AUTH_EXEMPT` carve-out checked first.

### Graceful degradation / never-crash on missing optional capability
**Source:** `flowstate/embeddings.py:1-6` (module contract), `flowstate/pack.py:90-98` (Result-with-error-message-not-exception)
**Apply to:** Every fallback rung in `sandbox.py`'s degradation ladder (bwrap absent → observe; landlock unavailable → bwrap-only; unsupported platform → env-scrub only) — never raise, always return a usable `(argv, env)`.

### Module docstring convention (contract-first, doctest-style public API block)
**Source:** `flowstate/bridge.py:1-23`, `flowstate/embeddings.py:1-19`
**Apply to:** `sandbox.py`'s top-of-file docstring — state the `observe`-never-blocks contract in the first sentence, show `wrap()`'s call shape as a code block, cross-reference D-01..D-04 by ID (matching how `bridge.py`'s docstring cross-references its own spike, `260525-o6h`).

### `from __future__ import annotations` + PEP 604 unions
**Source:** every module header in `flowstate/` (e.g. `bridge.py:25`, `embeddings.py:21`, `pack.py:10`)
**Apply to:** `sandbox.py` — `list[str]`, `dict[str, str]`, `Path | None`, no `Optional`/`Union` imports.

## No Analog Found

| File/Concept | Role | Data Flow | Reason |
|--------------|------|-----------|--------|
| Linux `ctypes` raw syscall wrapper (`landlock_create_ruleset`/`landlock_add_rule`/`landlock_restrict_self`) | utility (Linux-only) | syscall/event-driven | No existing platform-detection or raw-syscall code anywhere in `flowstate/` (confirmed via RESEARCH.md's own grep — `sys.platform`/`platform.*` unused in source prior to this phase). Use RESEARCH.md's own verified-working code example (Code Examples section, "Verified: minimal ctypes Landlock ruleset") as the pattern source instead of a codebase analog — it is itself the analog, sourced from the prior on-disk spike and cross-checked against `/Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx/agent-sbx-landlock/main.go`. |
| macOS SBPL profile string builder | utility (macOS-only) | transform | No existing SBPL/Seatbelt code in `flowstate/`. Pattern source is `/Users/jhogan/sandflox/sbpl.go` (external reference repo, not a FlowState file) — cited in RESEARCH.md Pattern 1 with the exact target shape already extracted. |

## Metadata

**Analog search scope:** `flowstate/*.py` (bridge.py, pack.py, gsd_vendor.py, embeddings.py, config.py), `tests/test_pack.py`, `tests/test_bridge.py`, `tests/test_embeddings.py`, `tests/test_context_prefix.py`
**Files scanned:** ~9 (5 source modules, 4 test modules), plus RESEARCH.md's own extracted code examples treated as first-class pattern sources where no in-repo analog exists (Linux ctypes syscalls, macOS SBPL string)
**Pattern extraction date:** 2026-07-12
**Note on scope:** This phase builds the seam and profile BUILDERS only (SBX-02) — it does not wire `wrap()` into the 8 call sites (`bridge.py:308`, `pack.py:115`, `distiller.py:92`, `tools/base.py:73`, `discipline.py:43/53/63/92`, `gsd_vendor.py:325/376`, Phase 24/SBX-03). No patterns for those call-site diffs are mapped here by design — `bridge.py`'s env-scrub block is cited only as the *shape* `_scrub_env()` generalizes, not as a file this phase modifies.
