# Phase 23: Linux Parity + Core Seam - Research

**Researched:** 2026-07-12
**Domain:** OS-level process sandboxing (macOS Seatbelt / Linux bwrap+Landlock), Python ctypes syscalls, env hygiene
**Confidence:** HIGH — the gating unknown (Linux Landlock via pure ctypes, zero new dependencies) has a reproducible, empirically-verified proof-of-concept on disk from a same-day prior research pass; this session independently re-verified the two most load-bearing factual claims (Landlock syscall numbers, Linux `claude` credential storage) against primary/official sources and found one previously-unflagged, load-bearing pitfall (see Pitfall 1).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**env-scrub policy (`observe` tier)**
- **D-01: Denylist, not allowlist.** The `observe` tier strips known-secret patterns from the child environment (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `AWS_*`, `GITHUB_*`, and similar credential-shaped vars) and passes everything else through. Rationale: `observe` must *never* break a subprocess (that's its whole contract as the non-blocking default); an allowlist risks starving `repomix`/`npx`/`git` of environment they legitimately need. Accepted risk: a novel, non-pattern-matching secret var could slip through — acceptable for the `observe` tier, whose job is env hygiene, not hard confinement. (An allowlist may still be used inside `confine` later — that's a Phase-25 concern.)
- Reference sandflox `env.go` for the scrub pattern set, but reimplement natively.

**Linux confinement depth (SBX-01 spike + profile builder)**
- **D-02: bwrap + landlock (defense-in-depth now).** The Linux tier layers landlock LSM path rules on top of the bwrap mount namespace, matching sandflox's `agent-sandbox-demos/agent-sbx` design — chosen over bwrap-only. **Consequence (load-bearing for the spike):** SBX-01 must prove that *both* the mount-namespace write confinement *and* the landlock path rules preserve `claude` auth/API reachability, not just bwrap alone. **Kernel constraint:** landlock needs Linux ≥ 5.13; on older kernels the profile builder must degrade (to bwrap-only, or to `observe` if bwrap is also unavailable) rather than hard-fail. Capture the kernel-version detection + degradation ladder as part of the spike findings.

**Linux spike-failure posture (SBX-01 outcome)**
- **D-03: Asymmetric degrade.** If the Linux spike cannot preserve `claude` auth under bwrap+landlock, macOS `confine` still ships (the macOS mechanism is spike-proven), and Linux `confine` becomes a warned observe-only path ("kernel confinement pending") rather than blocking the whole tier. Honors SEED-003's "a failed spike is a valid outcome" and still ships the guardrail on the proven platform. This is the *contingency*; the goal remains full Linux parity.

**`wrap()` return contract (SBX-02 seam shape)**
- **D-04: Return a transformed `(argv, env)` tuple.** `wrap(cmd, surface, project_root, env)` returns the (possibly sandbox-prefixed) argv and the scrubbed env; each future call site (Phase 24) becomes `cmd, env = wrap(cmd, surface, project_root, env)` followed by the existing `subprocess.run(cmd, env=env, ...)`. Chosen over a callable-that-executes or a context-manager because it's the smallest per-site diff (~2 lines), keeps each site's varied `subprocess.run` kwargs untouched, is trivially unit-testable (assert argv/env transform without spawning), and inverts no control flow.

### Claude's Discretion
- The exact denylist pattern set (D-01) — start from sandflox `env.go`, expand with obvious credential shapes; the researcher/planner finalizes the list. **This research finalizes a concrete list — see Common Pitfalls, Pitfall 1 and Code Examples.**
- The internal module layout of `flowstate/sandbox.py` (platform-split functions à la sandflox's `exec_darwin.go`/`exec_other.go`, profile-builder helpers) — implementation detail. **This research recommends a single flat module — see Recommended Project Structure.**
- Whether `observe`-tier env-scrub is applied inside `wrap()` unconditionally or only when a tier is set — planner's call, but the Phase-23 default posture is `observe`.
- The precise landlock ruleset expression and the kernel-version detection method (D-02). **This research provides a verified-working ctypes implementation — see Code Examples.**

### Deferred Ideas (OUT OF SCOPE)
- Threading `wrap()` into the 8 subprocess sites — Phase 24 (SBX-03).
- `ProjectPreferences.sandbox` config field — Phase 24 (SBX-04).
- The `confine` tier's real production profiles + E2E denial proof (write-outside-root denied, `~/.ssh` read denied, auth survives) — Phase 25 (SBX-05).
- Fail-loud on missing sandbox binary under `confine` — Phase 25 (SBX-06).
- Network egress allowlisting — out of scope milestone-wide (the network paradox); tracked as SBX-F1.
- Windows sandbox tier — out of scope; SBX-F2.
- Allowlist env-scrub inside `confine` — possible Phase-25 refinement; `observe` uses the denylist (D-01).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SBX-01 | A Linux `bwrap`+landlock spike proves an allow-default + selective-deny profile preserves `claude` auth and API reachability (mirroring the passed macOS Seatbelt spike), or honestly documents the parity gap and its consequence for later phases. A failed spike is a recorded outcome, not a silent skip. | Linux auth model confirmed structurally simpler than macOS (plain file `~/.claude/.credentials.json`, mode 0600, vs. Keychain mach-lookup) — see State of the Art. Verified-working ctypes Landlock proof-of-concept — see Code Examples. Landlock syscall numbers (444/445/446) independently confirmed identical on x86_64 and arm64 via two separate web searches this session. Real-world degradation-ladder gap identified (Ubuntu 24.04+ AppArmor userns restriction is the dominant bwrap failure mode, not kernel version) — see Pitfall 3. Reproducible spike environment recipes (Docker / Lima) documented — see Environment Availability. |
| SBX-02 | `flowstate/sandbox.py` exposes a single `wrap(cmd, surface, project_root, env)` seam with per-platform profile builders; the default `observe` tier is env-scrub only and never blocks a command. Unit-tested against a fake command; profile emission golden-tested. | `wrap()` seam shape and pure-builder pattern derived directly from D-04 — see Architecture Patterns, Pattern 1 & 2. Concrete, finalized env-scrub denylist pattern set with a critical auth-var carve-out this research discovered (naively porting sandflox's exact-block list would break FlowState's own headless auth) — see Common Pitfalls, Pitfall 1. Module layout recommendation (flat `flowstate/sandbox.py`) — see Recommended Project Structure. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

From `/Users/jhogan/frameworx/CLAUDE.md` (checked into the codebase) and `/Users/jhogan/frameworx/.claude/CLAUDE.md`:

- **No new core runtime dependencies** in this milestone — directly satisfied by the ctypes-stdlib-only approach; this is the load-bearing constraint that rules out `py-landlock`/`landlock` PyPI packages regardless of their individual legitimacy.
- **Python 3.12+**, Click for CLI, Pydantic for state, SQLite+FTS5 for memory — `flowstate/sandbox.py` has no CLI/state/memory surface in this phase (that's Phase 24), so this mostly constrains syntax (PEP 604 `|` unions via `from __future__ import annotations`, matching every other module in `flowstate/`).
- **Coverage ≥80%** enforced by `pyproject.toml --cov-fail-under=80`. The `observe` tier's pure-function shape (Pattern 2) makes this easy to hit without spawning subprocesses; the Linux-only ctypes path needs `sys.platform` guards so it doesn't tank coverage when tests run on this (Darwin) development machine — plan for `# pragma: no cover` or platform-skip markers on the Linux-only branches, consistent with `tests/conftest.py`'s existing `@pytest.mark.slow`/`@pytest.mark.integration` marker convention.
- **ruff** (line length 100, double quotes, 4-space indent) — matches every existing `flowstate/*.py` file; no special-casing needed.
- **Naming/style conventions**: lowercase snake_case module (`sandbox.py`), private helpers prefixed `_` (`_scrub_env`, `_wrap_macos`, `_wrap_linux`), Result-object-not-exception error handling matching `BridgeResult`'s pattern (though `wrap()` itself, per D-04, never fails hard — it degrades, consistent with the house style "graceful-degradation-not-crash" already used for `repomix`-absent and `[semantic]`-absent paths).
- **GSD Workflow Enforcement**: file changes for this phase's actual implementation must go through `/gsd:execute-phase`, not direct edits — not a research concern, but the planner should structure tasks accordingly.
- No file logging; Rich-console-only output style — if `sandbox.py` needs to warn (e.g., "bwrap unavailable, falling back to observe"), match the existing `stderr`/Rich pattern used elsewhere in the codebase rather than introducing `logging`.

## Summary

The Linux confinement unknown (SBX-01) is **resolvable, not just researchable**. A same-day prior research pass in this repo (on-disk at this exact file path, uncommitted) built and ran a working proof: a ~90-line pure-`ctypes` Python script applied a Landlock ruleset (syscalls 444/445/446) inside a Docker-Desktop Linux VM (kernel 6.12.76, arm64, Landlock ABI v6) and correctly allowed writes to `/tmp` while denying writes to `/root`. This session independently re-verified the two claims that finding depends on most: (1) Landlock syscall numbers 444/445/446 are confirmed identical on x86_64 *and* arm64 via two separate primary-source-grounded web searches (kernel patchwork series, syscall.sh reference tables) — arm64 uses the same generic syscall table, so no per-arch branching is needed in the ctypes wrapper; (2) Linux `claude` stores OAuth credentials in a plain file, `~/.claude/.credentials.json` (mode `0600`), confirmed against `code.claude.com/docs/en/authentication` and cross-referenced with `support.claude.com`'s API-key-env-var documentation — structurally *simpler* to preserve under confinement than macOS's opaque Keychain mach-lookup (a read-rule on one file + normal HTTPS egress, not a system-service reachability problem).

This session also surfaced a **previously-unflagged, load-bearing pitfall**: `claude --print` supports two additional headless auth mechanisms beyond the Keychain/file OAuth flow — `ANTHROPIC_API_KEY` (direct API-key auth, explicitly recommended by Anthropic for CI/headless/SSH environments) and `CLAUDE_CODE_OAUTH_TOKEN` (a long-lived token from `claude setup-token`, also explicitly recommended for CI). Both are exactly the shape D-01's denylist is designed to strip (`ANTHROPIC_API_KEY` matches sandflox's exact-blocked `ANTHROPIC_API_KEY` entry *and* its `ANTHROPIC_` prefix rule; `CLAUDE_CODE_OAUTH_TOKEN` matches the generic `*_TOKEN` wildcard named in D-01 itself). A naive port of sandflox's `env.go` pattern vocabulary would silently violate D-01's own explicit contract ("`observe` must never break a subprocess") for any FlowState user or CI pipeline authenticated via API key or OAuth token rather than interactive Keychain login — this is FlowState's *own* subprocess auth mechanism, not a third-party secret. See Pitfall 1 for the required carve-out.

**Primary recommendation:** Implement `flowstate/sandbox.py` as a single flat module (matching the codebase's flat-file convention) with pure, I/O-free profile-builder functions for macOS SBPL and Linux bwrap-args (golden-testable), a Linux-only ctypes Landlock helper (import-guarded on `sys.platform`), a denylist env-scrub reusing sandflox `env.go`'s pattern-set *vocabulary* (inverted to denylist-with-passthrough, since `env.go` is itself an allowlist — see Pitfall 2) with an explicit carve-out for `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN`/`CLAUDE_CONFIG_DIR`, and a `wrap(cmd, surface, project_root, env) -> (argv, env)` seam whose `observe` tier never touches `subprocess` at all. Run the actual SBX-01 spike using the Docker-Desktop recipe already verified on-disk (fastest available option on this machine), explicitly testing the file-based credential path (not just the token shortcut) since that's what Phase 24 will actually wire into `bridge.py`.

## Architectural Responsibility Map

FlowState is a CLI subprocess-orchestrator, not a web app — the standard Browser/SSR/API/CDN/DB tiers don't apply. The table below uses the tiers relevant to this phase's actual architecture.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Kernel confinement mechanism (Seatbelt / bwrap+Landlock) | OS / Kernel | — | Filesystem + env confinement is enforced by the kernel LSM/namespace primitives, not by Python code; Python only *constructs* the profile/argv |
| Profile/argv construction (`build_macos_profile`, `build_linux_bwrap_args`) | Sandbox Seam (`flowstate/sandbox.py`) | — | Pure string/list builders, no I/O — this phase's actual deliverable |
| Landlock ruleset application | Sandbox Seam (`flowstate/sandbox.py`, Linux-only path) | OS / Kernel | Python issues the `landlock_*` syscalls via ctypes; the kernel enforces them |
| env-scrub (`observe` tier, D-01) | Sandbox Seam (`flowstate/sandbox.py`) | — | Pure dict transform, in-process, no OS call |
| `wrap()` call sites (`bridge.py:308` etc.) | Caller / Integration | Sandbox Seam | Phase 24, not this phase — placement only, no wiring here |
| `ProjectPreferences.sandbox` config | State / Config (`flowstate/state.py`) | — | Phase 24 |
| Auth credential storage (Keychain / `.credentials.json`) | OS / External | — | Not owned by FlowState; the seam's job is to *preserve reachability* to it, never to read/write it directly |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ctypes` | stdlib (3.12) | Raw `landlock_create_ruleset`/`landlock_add_rule`/`landlock_restrict_self` syscalls on Linux | Zero new dependency; verified working in the on-disk prior spike. Matches D-02/D-04's "reimplement natively" instruction and the project's no-new-core-runtime-dependency rule. `[VERIFIED: on-disk executed spike + independently cross-checked syscall numbers against kernel patchwork/syscall-table sources this session]` |
| `subprocess` | stdlib | Invoking `sandbox-exec` (macOS) / `bwrap` (Linux) as external binaries | Already the project's exclusive process-spawn mechanism; `wrap()` only transforms `(argv, env)`, the caller still owns `subprocess.run()` (D-04) |
| `sys.platform` / `platform.system()` | stdlib | Platform dispatch (`darwin` vs `linux`) | No existing platform detection in the codebase (confirmed via grep in CONTEXT.md); this phase introduces it cleanly |
| `shutil.which` | stdlib | Locating `sandbox-exec`/`bwrap` binaries, mirroring `bridge.py`'s `_find_claude()` pattern | Existing project convention (`flowstate/bridge.py:154`) |
| `tempfile` | stdlib | Writing the macOS `.sb` profile to a temp path for `sandbox-exec -f <path>` (SBPL has no inline-string invocation mode) | `sandbox-exec` requires a file path, not stdin; sandflox's own `WriteSBPL()` does the same |

**Version verification:** All core stack entries are Python 3.12 stdlib — no registry lookup needed, no version drift risk. Landlock syscall numbers (444/445/446) verified this session via two independent web searches against kernel-patchwork and syscall-reference sources, confirming identical numbering on x86_64 and arm64 (arm64 uses the shared generic 64-bit syscall table — new syscalls like Landlock's are assigned the same number across architectures that use the generic table). `[VERIFIED: multi-source web search, 2026-07-12 — github.com/torvalds/linux syscall tables, kernel.org patchwork Landlock series, arm64.syscall.sh]`

**Installation:** None — no new packages. `bwrap` (bubblewrap) and `sandbox-exec` are OS binaries located PATH-style, same pattern as `claude`/`repomix`, not Python dependencies.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | — | This phase deliberately adds zero runtime dependencies |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ctypes raw Landlock syscalls | `py-landlock` (PyPI) — a pure-Python wheel wrapping the same syscalls | Rejected: adds a third-party dependency for ~12 raw syscalls FlowState can implement in ~100 lines (already proven working); violates the "no new core runtime dependency" project rule; a security-sensitive syscall wrapper is exactly the kind of code worth auditing in-tree rather than trusting to a small, unaudited-by-this-team package. `[ASSUMED: package existence/metadata from WebSearch/training, not independently security-audited by this team — package-name provenance rule applies]` |
| ctypes raw Landlock syscalls | `landlock` (PyPI, pre-1.0/dev-tagged) | Same rejection rationale; weaker legitimacy signal than a tagged release. `[ASSUMED]` |
| bind-mounting `~/.claude/.credentials.json` into the sandbox | Minting a `CLAUDE_CODE_OAUTH_TOKEN` via `claude setup-token` and passing it through env | The token approach is simpler for the *spike* (no file bind-mount, no Landlock read-rule needed for the credentials path) but does not exercise the production default (subscription users hit the file path, not the token path) — the spike should test **both**, file-path as the one that actually retires the risk Phase 24 depends on |
| `command -v bwrap` presence check | Functional smoke test (`bwrap --ro-bind / / -- /bin/true`) | Presence check is insufficient — a modern Ubuntu 24.04+ host can have `bwrap` installed and on PATH yet still fail via AppArmor's `apparmor_restrict_unprivileged_userns=1` (see Pitfall 3). Only a functional smoke test (matching `agent-sbx`'s `check_bwrap_available()`) catches this. |

## Package Legitimacy Audit

This phase installs **zero external packages** (core stack is 100% Python 3.12 stdlib: `ctypes`, `subprocess`, `sys`, `platform`, `shutil`, `tempfile`). The Package Legitimacy Gate protocol is therefore not triggered for any dependency this phase actually adds.

For completeness, the two PyPI alternatives evaluated and **rejected** (see Alternatives Considered) are recorded below for audit-trail purposes only — **neither is being installed or recommended**:

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `py-landlock` | PyPI | not independently verified this session | not checked (not being installed) | claimed `github.com/SebastienWae/py-landlock`, not independently confirmed | not run (no install planned) | **REJECTED — not installed.** Native ctypes reimplementation chosen instead per D-02/D-04 and the no-new-dependency rule. `[ASSUMED]` per package-name provenance rule. |
| `landlock` | PyPI | pre-release (`1.0.0.dev5` per prior pass, not re-verified) | not checked (not being installed) | not verified | not run (no install planned) | **REJECTED — not installed.** Same rationale; also a weaker legitimacy signal (dev-tagged). `[ASSUMED]` |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck not run — no installs).
**Packages flagged as suspicious [SUS]:** none.

*No `checkpoint:human-verify` gate is needed for package installs in this phase, because there are none. If a future phase (24/25) reconsiders adding `py-landlock`, run the full Package Legitimacy Gate at that time — including `pip install slopcheck` and `pip index versions py-landlock` against the real PyPI registry, neither of which this research triggered since no install is planned.*

## Architecture Patterns

### System Architecture Diagram

```
                    flowstate/bridge.py (Phase 24, NOT this phase)
                              │
                              │  cmd, env = wrap(cmd, "llm", project_root, env)
                              ▼
                 ┌────────────────────────────┐
                 │   flowstate/sandbox.py      │   ← THIS PHASE builds this
                 │                             │
                 │   wrap(cmd, surface,        │
                 │        project_root, env)   │
                 │        -> (argv, env)       │
                 └──────────────┬──────────────┘
                                │
                 tier lookup (default: observe)
                                │
              ┌─────────────────┴──────────────────┐
              │                                     │
        tier == observe                       tier == confine
              │                                     │
              ▼                                     ▼
     _scrub_env(env)  (D-01 denylist         platform dispatch (sys.platform)
     + Pitfall-1 auth carve-out)                     │
     argv unchanged                          ┌─────────┴──────────┐
     (no subprocess touched here)            ▼                     ▼
              │                       darwin: build           linux: build
              │                       _macos_profile()         _linux_bwrap_args()
              │                       -> write temp .sb        + _landlock ruleset
              │                       -> prefix argv with       via ctypes syscalls
              │                          sandbox-exec -f ...    -> prefix argv with
              │                                                    bwrap ...
              │                                     │
              └─────────────────┬───────────────────┘
                                 ▼
                     return (argv', env') tuple
                                 │
                    (Phase 24) caller does:
                    subprocess.run(argv', env=env', ...)
```

The kernel enforcement itself (Seatbelt / bwrap namespaces / Landlock rules) happens **inside the OS**, invisibly to `wrap()` — `wrap()`'s entire job in this phase is to *construct* the transformed `(argv, env)`; it never spawns a process (that's the caller's job, unchanged, per D-04).

### Recommended Project Structure

```
flowstate/
├── sandbox.py           # public wrap() seam, tier dispatch, D-01 env-scrub, platform-split profile builders
tests/
├── test_sandbox.py       # wrap() unit tests (fake command, no spawning); golden tests for profile builders
```

Recommend a **single flat `flowstate/sandbox.py`** (matches the codebase's flat-module convention — no existing subpackage precedent for a feature this size). Group the Linux-only ctypes syscall code (structs, syscall wrappers, ABI probing) behind a `sys.platform.startswith("linux")` import guard within the same file first; split into `flowstate/_landlock.py` only if the file grows past ~250–300 lines. This is Claude's Discretion per CONTEXT.md — flat-first is the recommendation, not a hard requirement.

### Pattern 1: Pure, I/O-free profile builders (golden-testable)

**What:** `build_macos_profile(project_root: Path) -> str` and `build_linux_bwrap_args(project_root: Path) -> list[str]` take only data in, return only data out — no filesystem writes, no syscalls, no subprocess calls inside the builder itself.
**When to use:** Every profile-emission function in this phase. This is *the* pattern that makes "profile emission golden-tested" (SBX-02's explicit requirement) trivial: assert exact string/list equality against a fixture.
**Example:**
```python
# Source: mirrors sandflox sbpl.go's GenerateSBPL() — "pure string from *ResolvedConfig...no I/O"
# (/Users/jhogan/sandflox/sbpl.go, local checkout, read 2026-07-12)
def build_macos_profile(project_root: Path) -> str:
    project = str(project_root)
    return f"""(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "{project}")
  (subpath "/private/tmp")
  (subpath "/private/var/folders")
  (subpath "/dev"))
(deny file-read* (subpath "{Path.home() / '.ssh'}"))
"""
```
The macOS spike (already passed, prior session, recorded in memory `flowstate-sandbox-spike`) proved this exact shape — `(allow default)` baseline, selective `(deny file-write*)` re-allow, `(deny file-read* (subpath ~/.ssh))` — preserves Keychain auth. **Deny-default breaks auth; this exact shape does not.**

### Pattern 2: `wrap()`'s `observe` tier never calls subprocess (D-04 corollary)

**What:** The `observe` tier is a pure `(argv, env)` transform. Because `wrap()` itself never spawns a process (the caller does, per D-04), `observe`-tier tests need **zero OS interaction** — no `subprocess`, no tmp files, no platform checks.
**When to use:** All `observe`-tier unit tests.
**Example:**
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

### Pattern 3: Functional smoke test for `bwrap` availability, never presence-check

**What:** `check_bwrap_available()` runs `bwrap --ro-bind / / -- /bin/true` and checks the exit code, rather than `shutil.which("bwrap")`.
**When to use:** Every point in the degradation ladder that decides "is bwrap usable here."
**Example:**
```python
# Source: /Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx/agent-sbx:147-152, read 2026-07-12
# check_bwrap_available() { command -v bwrap ... ; bwrap --ro-bind / / -- /bin/true 2>/dev/null || return 1 ; }
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

### Anti-Patterns to Avoid

- **Kernel-version-only gating:** Checking `platform.release()`/`uname -r` >= 5.13 and stopping there. The dominant real-world Linux bwrap failure (Ubuntu 24.04+ AppArmor userns restriction, Pitfall 3) has **nothing to do with kernel version** — a 6.8+ kernel host can still fail. Always pair the version/ABI check with the functional smoke test (Pattern 3).
- **Copying sandflox `env.go`'s allowlist architecture:** `env.go` is a default-deny **allowlist**, not a denylist. D-01 deliberately locks a **denylist** instead. Do not port the allowlist shape — port only the *pattern-set vocabulary* and invert the logic (see Pitfall 2).
- **Naively porting sandflox's exact-blocked-var list without an auth carve-out:** sandflox's `blockedExact`/`blockedPrefixes` blocks `ANTHROPIC_API_KEY` and any `*_TOKEN`-shaped var by design — correct for sandflox's own threat model (it isn't itself `claude`'s auth mechanism), **wrong** for FlowState, where `claude --print` *is* the wrapped subprocess and may itself be authenticated via exactly these vars. See Pitfall 1 — this is the single most important correction this research makes to a literal reading of CONTEXT.md's "reference sandflox env.go" instruction.
- **Assuming macOS's mach-IPC auth model applies to Linux:** it does not — Linux is a plain credentials file. Don't over-engineer the Linux profile with Seatbelt-style `mach-lookup` allowances; that's a macOS-only concept.
- **Catching only `PermissionError` for denied writes in spike/test code:** a *mount-namespace* denial (bwrap `--ro-bind`) surfaces as `OSError: [Errno 30] Read-only file system`, while a pure-Landlock denial surfaces as `PermissionError: [Errno 13]`. Any spike/test code asserting "the write was denied" must catch `OSError` broadly (or check `errno` in `{EACCES, EROFS, EPERM}`), not narrowly `PermissionError`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Argv shell-quoting for any `bash -c '...'` wrapping pattern (if ever needed) | A hand-rolled quoting function | Python's `shlex.quote()` (stdlib) | sandflox's Go `shellquote()` exists because Go has no stdlib equivalent; Python does — use it directly rather than porting sandflox's quoting logic |
| Landlock syscalls | *(inverted case — this is the one place hand-rolling is the locked, correct choice)* | `ctypes` raw syscalls, verified working in the on-disk prior spike | D-02/D-04 explicitly mandate native reimplementation over a dependency; the "don't hand-roll" instinct is correctly overridden here by the no-new-core-dependency project rule — call this out explicitly in the plan so a future reviewer doesn't "fix" it by importing `py-landlock` |

**Key insight:** This phase is the rare case where the *standard* advice ("don't hand-roll security primitives, use a vetted library") is deliberately inverted by a locked project decision (no new core dependency + native reimplementation, D-02/D-04). The mitigating factor: the syscall surface is small (3 syscalls, ~15 lines of raw wrapper code, verified working), auditable in-tree, and the actual security *enforcement* is done entirely by the kernel — the ctypes code only constructs and submits the ruleset, it does not implement any security logic itself.

## Common Pitfalls

### Pitfall 1: The env-scrub denylist can strip FlowState's own `claude` auth vars — requires an explicit carve-out (new finding, this session)
**What goes wrong:** D-01's denylist pattern set (`*_API_KEY`, `*_TOKEN`, `AWS_*`, plus sandflox `env.go`'s exact-blocked `ANTHROPIC_API_KEY` and prefix-blocked `ANTHROPIC_`) is designed to strip credential-shaped vars belonging to *other* tools the subprocess might touch (AWS, GitHub, Stripe, etc.). But `claude --print` — the primary `observe`-tier target (`bridge.py:308`) — supports two fully legitimate, Anthropic-documented headless auth mechanisms that match these exact patterns: `ANTHROPIC_API_KEY` (recommended for CI/SSH/headless environments, bypasses OAuth entirely) and `CLAUDE_CODE_OAUTH_TOKEN` (long-lived token from `claude setup-token`, also explicitly recommended for CI). A literal port of sandflox's pattern vocabulary strips both, silently breaking `claude` auth for any FlowState user or CI pipeline that isn't using interactive Keychain/file-based OAuth login — a direct violation of D-01's own stated contract ("observe must never break a subprocess").
**Why it happens:** CONTEXT.md's canonical-refs instruction ("reference sandflox `env.go` for the scrub pattern set") doesn't flag that sandflox's threat model treats `ANTHROPIC_*`/`*_TOKEN` purely as *other tools'* secrets — sandflox itself is never authenticated via those vars. FlowState's situation is structurally different: the wrapped subprocess (`claude`) may legitimately need exactly the vars that look most credential-shaped.
**How to avoid:** Add an explicit exemption list checked *before* the denylist match, so these names always pass through regardless of pattern match: `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR` (changes where `.credentials.json` is read from — not secret-shaped but auth-relevant, must not be dropped), and `ENABLE_PROMPT_CACHING_1H` (already set by `bridge.py` for cache-TTL control, not secret-shaped but worth confirming it isn't accidentally caught by a broad `*_1H`-style pattern — it isn't, but call it out in the test suite). Recommended pattern-set finalization: block-prefixes `AWS_`, `AZURE_`, `GCP_`, `GCLOUD_`, `SSH_`, `GPG_`, `DOCKER_`, `KUBE`, `GITHUB_`, `GITLAB_`, `BITBUCKET_`, `STRIPE_`, `TWILIO_`, `SENDGRID_`, `SLACK_`, `DISCORD_`, `DATABASE_`, `DB_`, `REDIS_`, `MONGO`; block-suffixes (wildcard) `_API_KEY`, `_TOKEN`, `_SECRET`, `_PASSWORD`, `_CREDENTIALS`; explicit block-exact `SECRET_KEY`, `PASSWORD`, `PASSWD`; then subtract the exemption list above from *any* match, prefix or suffix. Note this deliberately does **not** block a bare `ANTHROPIC_` prefix (unlike sandflox) — since FlowState's own auth lives there.
**Warning signs:** A `claude --print` call under `observe` tier that succeeds when run directly (`FLOWSTATE_CLAUDE_BIN` set, `ANTHROPIC_API_KEY` in env) but fails once routed through `wrap()` — this is the regression to test for explicitly, ideally as a named unit test (`test_observe_never_strips_claude_auth_vars`).

### Pitfall 2: sandflox `env.go` is an allowlist, not a denylist — do not port its architecture verbatim
**What goes wrong:** A naive reading of `env.go`'s doc comment ("BuildSanitizedEnv constructs a filtered environment... Only allowlisted variables pass through") plus CONTEXT.md's "reference sandflox env.go for the scrub pattern set" could lead to porting the allowlist *architecture*, silently breaking D-01's explicit "observe must never break a subprocess" contract (an allowlist WILL starve `git`/`npx`/`repomix` of env vars they need but aren't on sandflox's narrow list, e.g. `GIT_*`, `NODE_*`, `NPM_CONFIG_*`).
**Why it happens:** The *pattern set* (the credential-shaped name vocabulary) and the *architecture* (allowlist vs denylist) are different things; D-01 already resolved this by deliberately choosing the opposite architecture from sandflox's own.
**How to avoid:** Extract only the *vocabulary* from `env.go`'s `blockedPrefixes`/`blockedExact` (see Pitfall 1 for the finalized, FlowState-adjusted list) and invert to "strip if matches any of these minus the exemption list, pass everything else through."
**Warning signs:** Any test where a `repomix`/`npx`/`git` subprocess call fails under `observe` tier that passed before — that's the allowlist-vs-denylist regression.

### Pitfall 3: Ubuntu 24.04+ blocks unprivileged `bwrap` via AppArmor, not kernel version
**What goes wrong:** A "kernel >= 5.13" check reports the host is fully capable, but `bwrap` still fails at runtime with `bwrap: setting up uid map: Permission denied` on a fresh Ubuntu 24.04+ install (kernel 6.8+, well past 5.13).
**Why it happens:** Ubuntu 23.10+ ships `kernel.apparmor_restrict_unprivileged_userns=1` by default, which requires an AppArmor profile explicitly permitting `unshare(CLONE_NEWUSER)`. `bwrap` doesn't ship such a profile on all installs.
**How to avoid:** Always pair the kernel/ABI version check with the *functional* smoke test (Pattern 3, matching `agent-sbx`'s `check_bwrap_available()`). If the smoke test fails but Landlock is available (Landlock syscalls need no special capability, unlike `unshare`), the degradation ladder's "Landlock-only, no namespace isolation" rung (documented in `agent-sandbox-demos`' own platform matrix) is a real, tested-working fallback — see Open Questions for whether the planner should add this as a third rung beyond D-03's two-rung ladder (bwrap-only → observe).
**Warning signs:** `bwrap` present in `PATH`, `bwrap --version` succeeds, but any real invocation with `--unshare-*` flags fails.

### Pitfall 4: ctypes struct packing for `landlock_path_beneath_attr` needs explicit padding
**What goes wrong:** The C struct `struct landlock_path_beneath_attr { __u64 allowed_access; __s32 parent_fd; }` has trailing padding to 8-byte alignment (16 bytes total, not 12) on both x86_64 and arm64. A naive `struct.pack("Qi", access, fd)` (12 bytes) can work by accident on some systems but is not the documented ABI shape; getting the size wrong causes `landlock_add_rule` to return `EINVAL`.
**Why it happens:** Python's `struct` module doesn't auto-apply C struct alignment/padding rules the way a C compiler does; the padding bytes must be explicit.
**How to avoid:** Use `struct.pack("QiI", access, fd, 0)` (the trailing `I` is 4 bytes of explicit padding, total 16 bytes), or use `ctypes.Structure` subclasses (which handle alignment automatically) for the final implementation rather than raw `struct.pack`.
**Warning signs:** `landlock_add_rule` returns nonzero / sets `errno=EINVAL` despite a valid, existing path and a valid ruleset fd.

### Pitfall 5: `PR_SET_NO_NEW_PRIVS` must precede `landlock_restrict_self`
**What goes wrong:** Calling `landlock_restrict_self` without first calling `prctl(PR_SET_NO_NEW_PRIVS, 1)` can fail on some kernel configurations (Landlock requires the calling process to have `no_new_privs` set, matching the pattern used by seccomp-bpf).
**Why it happens:** Documented Landlock precondition, mirrored in both the Go `agent-sbx-landlock/main.go` reference (`PR_SET_NO_NEW_PRIVS` = 38, called immediately before `landlockRestrictSelf`) and the on-disk prior spike's Python script.
**How to avoid:** Always call `libc.prctl(38, 1, 0, 0, 0)` before `landlock_restrict_self`, exactly as both references do.
**Warning signs:** `restrict_self` failing intermittently in ways that don't correlate with ruleset content.

## Code Examples

### Verified: minimal ctypes Landlock ruleset (on-disk prior spike, tested end-to-end against a real Linux VM)

```python
# Verified working in a prior same-day research session: Docker Desktop LinuxKit VM,
# kernel 6.12.76-linuxkit, arm64, Landlock ABI v6, unprivileged container
# (no --privileged needed for this half — only bwrap needed it, see Pitfall 3).
# Syscall numbers independently re-confirmed this session (identical x86_64/arm64).
import ctypes, os, struct

libc = ctypes.CDLL(None, use_errno=True)
NR_landlock_create_ruleset = 444   # identical on x86_64 and arm64
NR_landlock_add_rule = 445
NR_landlock_restrict_self = 446
LANDLOCK_RULE_PATH_BENEATH = 1
READ_ACCESS = (1 << 0) | (1 << 2) | (1 << 3)   # EXECUTE | READ_FILE | READ_DIR
WRITE_ACCESS = (1 << 1) | (1 << 4) | (1 << 5) | (1 << 8)  # WRITE_FILE | REMOVE_DIR/FILE | MAKE_REG
FULL_ACCESS = READ_ACCESS | WRITE_ACCESS

ruleset_attr = struct.pack("QQ", FULL_ACCESS, 0)  # handled_access_fs, handled_access_net
buf = ctypes.create_string_buffer(ruleset_attr, len(ruleset_attr))
ruleset_fd = libc.syscall(NR_landlock_create_ruleset, ctypes.byref(buf), len(ruleset_attr), 0)

def add_rule(path, access):
    fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    attr = struct.pack("QiI", access, fd, 0)  # 16-byte padded struct (Pitfall 4)
    abuf = ctypes.create_string_buffer(attr, len(attr))
    libc.syscall(NR_landlock_add_rule, ruleset_fd, LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(abuf), 0)
    os.close(fd)

add_rule("/tmp", FULL_ACCESS)          # writable
for p in ("/usr", "/lib", "/bin", "/etc"):
    add_rule(p, READ_ACCESS)           # read-only

libc.prctl(38, 1, 0, 0, 0)             # PR_SET_NO_NEW_PRIVS (Pitfall 5)
libc.syscall(NR_landlock_restrict_self, ruleset_fd, 0)
# From here on: writes to /tmp succeed, writes anywhere else raise PermissionError.
```
Result observed in the prior spike: write to `/tmp` succeeded; write to `/root` raised `PermissionError: [Errno 13] Permission denied` (Landlock-only) or `OSError: [Errno 30] Read-only file system` (when layered under a `bwrap --ro-bind` mount — see Anti-Patterns).

### Reproducible spike environment recipe (documented in prior on-disk research)

```bash
# Landlock-only (no special privilege needed):
docker run --rm ubuntu:24.04 bash -c "apt-get update -qq && apt-get install -y -qq python3 && python3 /path/to/landlock_test.py"

# bwrap + Landlock combined (requires --privileged inside Docker — Docker's own nested
# seccomp policy blocks CLONE_NEWUSER even when the host kernel/AppArmor would allow it):
docker run --rm --privileged ubuntu:24.04 bash -c "
  apt-get update -qq && apt-get install -y -qq bubblewrap python3
  bwrap --ro-bind / / --bind /tmp /tmp --dev /dev --proc /proc \
        --unshare-pid --unshare-uts --unshare-ipc --die-with-parent \
        -- python3 /path/to/landlock_test.py
"

# For a result representative of bare-metal/CI Linux (not a nested container), prefer
# Lima (confirmed installed on this machine, `limactl --version` -> 2.0.3):
#   limactl create --name=sbx-spike template://ubuntu-24.04
#   limactl shell sbx-spike -- <same install + test steps, no --privileged needed>
```

### D-04 seam shape, with the Pitfall-1 auth carve-out (design target, not yet in repo)

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

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| macOS Keychain-based auth reachability assumption applied uniformly | Linux uses a plain `~/.claude/.credentials.json` file (mode 0600), not an OS credential service; `CLAUDE_CONFIG_DIR` relocates it | Confirmed via `code.claude.com/docs/en/authentication`, re-checked this session | Linux confinement's auth requirement is *simpler* than macOS's, not equally opaque — a file read-rule + network egress, not a mach-lookup allowance |
| `kernel >= 5.13` as the sole Linux-confinement gate (CONTEXT.md D-02's framing) | Functional smoke test required in addition — Ubuntu 24.04+'s AppArmor policy is now the dominant real-world blocker, independent of kernel version | Ubuntu 23.10+ (kernel.apparmor_restrict_unprivileged_userns default flipped) | The planner should treat "kernel ≥ 5.13" as necessary-but-not-sufficient; the ladder needs the smoke test regardless of detected kernel version |
| Assuming `AWS_*`/`*_TOKEN`/`ANTHROPIC_*` are always safe to strip in an env-scrub denylist | For a tool that itself wraps `claude`, `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` must be explicitly exempted | This session, cross-referencing Anthropic's own headless-auth docs against D-01's literal pattern set | Changes the finalized denylist shape (Pitfall 1) — this is new relative to both CONTEXT.md and the prior on-disk research pass, which did not flag this collision |

**Deprecated/outdated:** None encountered — `sandbox-exec` shows no deprecation stderr noise in the prior macOS spike (recorded in memory `flowstate-sandbox-spike`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `py-landlock` / `landlock` PyPI packages were evaluated only by metadata (name, version, source-repo URL from a prior pass) — not installed, not slopcheck-verified, not code-reviewed this session | Alternatives Considered / Package Legitimacy Audit | Low — both explicitly rejected and not recommended; risk only if a future planner reconsiders them without re-running the full gate |
| A2 | Docker Desktop's LinuxKit VM (kernel 6.12.76-linuxkit, arm64) is representative enough of a real Ubuntu/Debian Linux host for the *Landlock* half of the on-disk prior finding | Summary, Pitfall 3 | Medium — Landlock behavior should be kernel-version-driven and portable, but LinuxKit is a minimal, purpose-built VM; the AppArmor-restriction finding (Pitfall 3) was sourced from web research about real Ubuntu hosts, not independently reproduced on LinuxKit in that same session (LinuxKit's container had no AppArmor policy loaded — its bwrap failure there was Docker's own seccomp, a different mechanism) |
| A3 | Landlock ABI v6 (observed in the prior spike) fully covers ABI v1-v4's guarantees relevant to this phase (path-beneath rules); no regression checked between ABI versions | Summary | Low — ABI is additive by design (each version adds capability flags, never removes), a documented Landlock design property |
| A4 | `claude setup-token` (long-lived `CLAUDE_CODE_OAUTH_TOKEN`) is a viable simplification for the *spike specifically*; the production path must still handle the file-based credential case since that's the default for interactive `/login` users | Alternatives Considered, Pitfall 1 | Low — flagged explicitly as a spike-simplification option, not a production recommendation |
| A5 | No independent AppArmor-restriction test was run on this (macOS) machine — the Pitfall 3 finding is sourced from cross-referenced web search (Ubuntu Launchpad, VS Code issue tracker, sandbox-runtime issue tracker), not locally reproduced by any session's researcher | Pitfall 3 | Medium — high-confidence given cross-source agreement, but not locally reproduced |
| A6 | The Pitfall-1 auth-var carve-out list (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`) is complete — no other FlowState-relevant `claude` env var was identified as both credential-shaped and legitimately needed | Pitfall 1, Code Examples | Medium — sourced from official Anthropic auth docs read this session, but a future `claude` CLI release could add a new auth env var not covered here; the planner should treat this list as a starting point, not exhaustive forever |

**If this table is empty:** N/A — see entries above.

## Open Questions (RESOLVED)

**RESOLVED (Q1):** Implement exactly D-03's two rungs; the Landlock-only rung is REJECTED and recorded as a documented future refinement — resolved in plan 23-03 Task 2 (`_wrap_linux` two-rung ladder + explicit reject comment).
**RESOLVED (Q2):** The spike finding is recorded as a committed `23-SPIKE-LINUX.md` artifact with an unambiguous VERDICT — resolved in plan 23-04 (Docker mechanism spike + committed verdict).
**RESOLVED (Q3):** Test both the file-based (`~/.claude/.credentials.json`) and OAuth-token (`CLAUDE_CODE_OAUTH_TOKEN`) auth paths; the file path is the risk-retiring proof — resolved in plan 23-04 Task 2.

1. **Should the degradation ladder include a "Landlock-only, no namespace isolation" rung?**
   - What we know: CONTEXT.md's D-03 names exactly two fallback rungs — "bwrap-only, or observe if bwrap is also unavailable." `agent-sandbox-demos`' own documented matrix has a third row: "Landlock only (no bwrap): LSM FS enforcement, no namespace isolation." The prior on-disk spike found Landlock alone works even inside an *unprivileged* Docker container — Landlock is the *more* available of the two primitives in practice, since Pitfall 3's AppArmor userns restriction affects only `bwrap`, not Landlock.
   - What's unclear: Whether Landlock-only (FS confinement, no PID/UTS/IPC namespace isolation) meets the bar for the `confine` tier's *filesystem* confinement promise, or whether the milestone considers namespace isolation load-bearing enough that "Landlock without bwrap" should collapse straight to `observe`.
   - Recommendation: Surface this to the planner as a design decision, not something research should silently resolve — it changes the shape of `_wrap_linux()`'s fallback branching (3-way vs 2-way). Given D-03's literal two-rung wording, the safe default is to implement exactly D-03's two rungs and record the Landlock-only option as a documented future refinement, not silently add a third rung research invented.

2. **Where does the actual SBX-01 spike run, and is its finding recorded as a committed artifact?**
   - What we know: The prior on-disk research pass verified the *mechanism* works (ctypes Landlock, bwrap+Landlock combined) on this developer's Docker Desktop VM. `limactl` is also available (confirmed `2.0.3`) and would give a more representative, non-nested-container result, but has not been exercised.
   - What's unclear: CONTEXT.md doesn't specify a target spike environment or how findings should be recorded (a spike-log markdown file alongside `23-CONTEXT.md`? a `checkpoint:human-verify` task requiring the user to run it themselves, mirroring how the macOS spike was run ad-hoc and only later memorialized in memory)?
   - Recommendation: The planner should decide the spike's recorded-artifact form (likely a `23-SPIKE-LINUX.md` or equivalent, mirroring "a failed spike is a recorded outcome") and whether it runs via Docker (fast, already proven, `--privileged` caveat for the bwrap half) or Lima (slower to provision, more representative of a bare Linux host, not yet exercised).

3. **Does the auth-preservation half of the spike need a real logged-in `claude` binary inside the Linux environment, or does the OAuth-token-passthrough shortcut (A4) satisfy SBX-01's proof bar?**
   - What we know: `claude setup-token` mints a token usable via `CLAUDE_CODE_OAUTH_TOKEN` without any file bind-mount — fast to test.
   - What's unclear: Whether SBX-01's "preserves claude auth and API reachability" requirement is satisfied by proving network+env reachability alone (token path), or whether it specifically requires proving the **file-based** `~/.claude/.credentials.json` read path survives confinement (since that's the default most subscription users hit in production, per `bridge.py`'s real call site).
   - Recommendation: Test both; treat the file-path test as the one that actually retires the risk (it's what Phase 24 will wire into `bridge.py`), and the token-path test as a fast smoke-check / fallback if installing+logging-in a fresh `claude` binary inside the spike environment proves too slow or requires interactive browser auth incompatible with a headless VM/container.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Desktop | Linux spike environment (nested-container approach) | Yes — confirmed in prior on-disk research | 29.4.1, LinuxKit VM kernel 6.12.76 (arm64) | Lima (below) for a non-nested result |
| Lima (`limactl`) | Linux spike environment (real-VM approach, avoids Docker's nested-seccomp caveat) | Yes — installed (`limactl --version` → `2.0.3`) | 2.0.3 | Not needed — no fallback required, not yet exercised |
| `bwrap` (bubblewrap) inside a Docker Ubuntu 24.04 image | SBX-01 spike, D-02 Linux confine tier | Yes — installable via `apt-get install bubblewrap` inside the container | `0.9.0` (per prior research) | N/A |
| Landlock kernel support | SBX-01 spike, D-02 Linux confine tier | Yes — Landlock ABI v6 confirmed inside the Docker VM (above the v1 minimum for kernel 5.13, and the v4 minimum for network rules) | ABI v6 | Degrade to bwrap-only or observe per D-03 on older kernels — not exercised (this machine's VM kernel is already 6.12) |
| `sandbox-exec` | macOS `confine` tier (already spike-proven, prior session) | Yes (macOS system binary, `/usr/bin/sandbox-exec`) | n/a — presence-checked in prior spike | N/A |
| `py-landlock` / `landlock` (PyPI) | Not required — evaluated and rejected | N/A (deliberately not installed) | n/a | ctypes native implementation (this phase's actual choice) |

**Missing dependencies with no fallback:** none.

**Missing dependencies with fallback:** none — every dependency this phase touches was either already present or has a documented, verified fallback path.

## Security Domain

`security_enforcement` is not explicitly disabled in `.planning/config.json` (absent = enabled). This phase's entire purpose is a security control, so this section is unusually load-bearing rather than boilerplate.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V1 Architecture, Design and Threat Modeling | Yes | The `wrap()` seam itself *is* the threat-modeled control (blast-radius reduction for prompt-injected/misbehaving subprocess calls); D-01/D-02/D-03/D-04 are the documented threat-model decisions |
| V6 Cryptography | No (indirect) | This phase does not implement cryptography; it must not degrade the OS's existing credential protection (Keychain encryption / file-mode 0600) by, e.g., copying credentials into a world-readable temp path |
| V8 Data Protection | Yes | The Linux credentials file (`~/.claude/.credentials.json`, mode 0600) and macOS Keychain must never be logged, echoed into generated profile files, or copied to a less-restrictive location by the sandbox builder code |
| V10 Malicious Code | Yes | This is precisely the threat this phase defends against — prompt-injected agent output attempting to write outside `project_root` or read `~/.ssh`/credentials; the guardrail is the mitigation |
| V12 Files and Resources | Yes | Filesystem confinement (write-outside-project-root denial, `~/.ssh` read denial) is V12's core concern; the macOS and Linux profile builders are the standard control |
| V14 Configuration | Yes | Fail-safe defaults: `observe` (non-blocking) is correctly the default per D-02/SBX-02; graceful degradation (never hard-fail on missing sandbox binary in `observe`, though `confine` fail-loud is explicitly Phase 25's SBX-06, not this phase's job) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Prompt-injected agent writes outside `project_root` | Tampering | `confine` tier's filesystem write-deny (macOS SBPL `deny file-write*` re-allow list; Linux bwrap `--ro-bind` + Landlock `WRITE_ACCESS` rules scoped to `project_root`) |
| Prompt-injected agent reads `~/.ssh`/credentials to exfiltrate | Information Disclosure | macOS SBPL `deny file-read* (subpath ~/.ssh)`; Linux bwrap `--ro-bind /dev/null <credential-path>` (credential masking) + Landlock read-rule omission (default-deny) |
| Env var leakage of unrelated secrets (`AWS_*`, `STRIPE_*`, etc.) into a subprocess that doesn't need them | Information Disclosure | D-01's `observe`-tier denylist env-scrub, applied unconditionally, minus the Pitfall-1 auth carve-out |
| **New:** env-scrub denylist itself strips `claude`'s own auth vars, breaking the tool while trying to protect it | Denial of Service (self-inflicted) | Pitfall 1's explicit `_AUTH_EXEMPT` carve-out, tested via a named regression test (`test_observe_never_strips_claude_auth_vars`) |
| Sandbox silently no-ops when the platform binary is missing, giving a false sense of confinement | Tampering / Repudiation | **Deferred to Phase 25 (SBX-06)** — fail-loud under `confine` is out of scope for this phase; note in the plan that `confine`'s profile-builder functions built here should not silently degrade without a caller-visible signal once Phase 25 wires them up |
| Struct-packing bug in the Landlock ctypes wrapper silently applies a weaker-than-intended ruleset (Pitfall 4) | Tampering | Golden/unit tests asserting exact ruleset byte-shape and behavioral tests (write-allowed/write-denied assertions), not just "no exception raised" |

## Sources

### Primary (HIGH confidence)
- `code.claude.com/docs/en/authentication` — Linux credential storage path (`~/.claude/.credentials.json`, mode 0600), `CLAUDE_CONFIG_DIR` override, `claude setup-token` for long-lived tokens `[CITED]`
- `support.claude.com/en/articles/12304248-manage-api-key-environment-variables-in-claude-code` — `ANTHROPIC_API_KEY` behavior, X-Api-Key header, headless/CI recommendation `[CITED]`
- GitHub `torvalds/linux` syscall tables (`arch/x86/entry/syscalls/syscall_64.tbl`) and kernel-hardening patchwork series ("arch: Wire up Landlock syscalls") — Landlock syscall numbers 444/445/446, confirmed identical across x86_64 and the generic table used by arm64 `[VERIFIED: primary kernel-source-adjacent references, cross-checked via two independent web searches this session]`
- `man7.org/linux/man-pages/man2/landlock_create_ruleset.2.html` — Landlock introduced in Linux 5.13; ABI versioning via `LANDLOCK_CREATE_RULESET_VERSION` flag `[CITED]`
- Local file reads, this session and prior same-day pass: `/Users/jhogan/sandflox/env.go`, `/Users/jhogan/sandflox/sbpl.go`, `/Users/jhogan/sandflox/exec_darwin.go`, `/Users/jhogan/sandflox/exec_other.go`, `/Users/jhogan/sandflox/agent-sandbox-demos/README.md`, `/Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx/agent-sbx`, `/Users/jhogan/sandflox/agent-sandbox-demos/agent-sbx/agent-sbx-landlock/main.go`, `/Users/jhogan/frameworx/flowstate/bridge.py`
- On-disk prior-session artifact (uncommitted, same date): a `ctypes`-based Landlock ruleset applied inside a Docker Desktop Ubuntu 24.04 container (kernel 6.12.76-linuxkit, arm64, Landlock ABI v6); combined bwrap+Landlock test under `--privileged`. This session did not re-execute the spike but independently re-verified its two most load-bearing factual claims (syscall numbers, Linux auth-file location) against fresh primary/official sources.

### Secondary (MEDIUM confidence)
- Ubuntu 24.04 AppArmor unprivileged-userns-restriction affecting `bwrap`: cross-referenced (in prior pass) across Ubuntu Launchpad bug #2046477, VS Code issue #316046, `anthropic-experimental/sandbox-runtime` issue #74 — independent sources agreeing on root cause and fix; not independently re-verified this session `[CITED, inherited]`
- `pypi.org` package metadata for the rejected `py-landlock`/`landlock` alternatives — name-only, not independently confirmed this session `[ASSUMED]`

### Tertiary (LOW confidence)
- None used as load-bearing this session.

## Metadata

**Confidence breakdown:**
- Standard stack (ctypes-only, zero new deps): HIGH — on-disk executed proof plus this session's independent re-verification of syscall numbers against primary sources
- Linux auth model (file-based credentials + API-key/OAuth-token headless paths): HIGH — sourced from current official Anthropic documentation, fetched and cross-checked this session; this is also the source of the new Pitfall 1 finding
- bwrap/AppArmor degradation-ladder gap (Pitfall 3): MEDIUM-HIGH — strong multi-source agreement from a prior pass, not independently re-verified this session (no AppArmor-capable host available)
- Architecture patterns (pure-builder, D-04 seam shape): HIGH — directly derived from locked D-01..D-04 decisions plus verified sandflox/agent-sbx reference code
- Security domain / ASVS mapping: MEDIUM — adapted from general ASVS categories to a CLI-sandboxing context ASVS doesn't natively model well; reasoned, not sourced from an ASVS-for-CLI-tools reference (none found)

**Research date:** 2026-07-12
**Valid until:** 30 days for the architecture/pattern findings (stable); the Ubuntu AppArmor-restriction finding and any specific kernel/ABI version numbers should be re-verified if the actual SBX-01 spike runs on a materially different Linux distribution/version than assumed here. The Pitfall 1 auth-carve-out list should be re-checked against `claude` CLI release notes if a major version bump occurs before Phase 24 wires this in.
</content>
