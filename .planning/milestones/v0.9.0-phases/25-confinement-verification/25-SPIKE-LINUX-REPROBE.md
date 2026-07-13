---
status: complete
phase: 25-confinement-verification
plan: 04
requirement: SBX-05
verdict: FIX-APPLIED
date: 2026-07-12
---

# 25-SPIKE-LINUX-REPROBE.md — WR-03 Re-probe (D-02) + D-03 Denial E2E

Re-runs the confined `claude --print` probe from `23-SPIKE-LINUX.md` with the two production
shortcuts that spike deliberately took (writable `HOME`, token-path credential) replaced by the
EXACT shipped `build_linux_bwrap_args(project_root)` argv (read-only `HOME` under `--ro-bind / /`)
and the FILE-based `~/.claude/.credentials.json` (0600) — the real `bridge.py` default. Both the
D-02 WR-03 re-probe and the D-03 Linux denial E2E share one Docker container run, per
`25-CONTEXT.md`.

## 1. Environment

- **Host:** macOS (Darwin 25.5.0), Docker Desktop 29.4.1
- **Container base image:** `ubuntu:24.04`, run `--rm` (throwaway, no project dependency added —
  per threat register T-25-SC, mirrors T-23-SC)
- **Kernel (inside container):** `6.12.76-linuxkit`, `aarch64`
- **bubblewrap:** 0.9.0 (installed via `apt-get install bubblewrap`)
- **claude CLI:** 2.1.207 (Claude Code), installed via the npm fallback (`@anthropic-ai/claude-code`)
  — same npm-fallback path the 23-spike used
- **Container privilege:** `--cap-add=SYS_ADMIN --security-opt seccomp=unconfined
  --security-opt apparmor=unconfined` (bwrap's mount-namespace unshare requires this on this
  Docker Desktop/linuxkit host; `--privileged` was not available in this execution environment,
  the narrower cap/seccomp/apparmor combination was sufficient and is the minimal privilege that
  let `bwrap` create its mount namespace)

## 2. Argv + credential used (D-02 — exact shipped shape)

The full confined argv was composed as `_find_bwrap()` (`bwrap` on `PATH` inside the container) +
`build_linux_bwrap_args(project_root)` (imported from the shipped `flowstate/sandbox.py`, called
with `project_root=/workspace/project`) + `["--", "claude", "--print", "reply with only the digit
4"]` — mirroring `_wrap_linux`'s composition (`bwrap_prefix + target`, `sandbox.py:596/613`), not a
hand-copied argv.

`build_linux_bwrap_args` produced (host-side confirmation, same shape used in-container):

```
--ro-bind / /
--bind <project_root> <project_root>
--tmpfs /tmp
--tmpfs <home>/.ssh
--dev /dev
--proc /proc
--unshare-pid
--unshare-uts
--unshare-ipc
--die-with-parent
```

(The `--tmpfs /tmp` entry is the fix this re-probe added — see Section 5.) `$HOME` (`/root` in the
container) stayed under the read-only `--ro-bind / /` root throughout; **no** `--setenv HOME
/tmp/chome` writable-HOME shortcut and **no** `CLAUDE_CODE_OAUTH_TOKEN` token-path shortcut were
used anywhere in this probe.

**Credential:** a working `~/.claude/.credentials.json` (0600, file-based OAuth blob — the
production `bridge.py` default) was mounted **read-only** into the container at
`/root/.claude/.credentials.json` via `docker run -v <host-path>:/root/.claude/.credentials.json:ro`.
The credential value was never echoed, printed, passed as a CLI arg, or written into any file
under version control — only its filename and Unix permissions (`-rw------- 1 root root 510
.credentials.json`) were captured, confirming presence/mode without exposing content. The
throwaway credential file was deleted from the host at the end of this task (`rm -f
/tmp/claude-creds.json`).

## 3. First attempt — FAILED for a filesystem-write reason (triggers the D-02 fix branch)

Confined `claude --print` under the **unmodified** shipped argv (no `--tmpfs /tmp`):

```
=== (a) CONFINED CLAUDE AUTH PROBE ===
EROFS: read-only file system, mkdir '/tmp/claude-0'
EXIT_CODE_CLAUDE=1
```

Root cause: `claude` writes its own scratch/session directory under `/tmp` (`/tmp/claude-0`)
regardless of `$HOME` — a filesystem-write failure, not an auth failure. Per the D-02 decision
gate, this is exactly the "confined claude fails for a filesystem-write reason" branch: the
minimal bound-writable fix must be applied and re-verified, not a speculative loosening.

Sanity checks in the same failed-attempt run confirmed the mount-namespace confinement itself was
already working correctly even before the fix:
- confined write **inside** `project_root`: succeeded (exit 0)
- confined write **outside** `project_root` (target `/tmp`, unbound): denied — `bash: line 1:
  /tmp/outside_test.txt: Read-only file system` (EROFS), file absent afterward
- confined read of `~/.ssh` (a decoy key planted at `/root/.ssh/id_rsa_decoy` before confinement):
  denied — `cat: /root/.ssh/id_rsa_decoy: No such file or directory` (the `--tmpfs
  <home>/.ssh` shadow makes the real directory's contents invisible inside confinement)

## 4. Fix applied — minimal writable `/tmp` scratch mount

Added `--tmpfs /tmp` to `build_linux_bwrap_args` (`flowstate/sandbox.py`), inserted between the
`--bind project_root project_root` pair and the existing `--tmpfs <home>/.ssh` entry. This mirrors
the macOS profile's already-shipped `/private/tmp` allow-write entry (`build_macos_profile`,
`sandbox.py:259`) — Linux gets an analogous private writable `/tmp`, implemented as a private
ephemeral tmpfs (not a `--bind` of the real host `/tmp`) so confinement stays tighter: the confined
process gets a scratch `/tmp` to write into, but never sees the real host `/tmp`'s contents. `$HOME`
itself is untouched — it remains read-only under `--ro-bind / /`; only `/tmp` and `~/.ssh` get
their own private tmpfs mounts.

`tests/test_sandbox.py`'s golden test (`TestBuildLinuxBwrapArgs::test_matches_golden_shape`) was
updated to the new exact arg list (`--tmpfs`, `/tmp` inserted before the existing `--tmpfs`,
`<ssh_dir>` pair); `test_contains_tmpfs_ssh_shadow` was corrected to locate the ssh tmpfs pair by
the ssh path itself (rather than the now-ambiguous first `--tmpfs` occurrence), and a new
`test_contains_tmpfs_tmp_scratch` test asserts the `/tmp` tmpfs entry is present.

## 5. Re-probe — PASSED with the fix applied

Same container recipe, same credential, argv rebuilt from the patched `build_linux_bwrap_args`
(now including `--tmpfs /tmp`):

```
=== (a) CONFINED CLAUDE AUTH PROBE with --tmpfs /tmp added ===
4
EXIT_CODE_CLAUDE=0
```

Real model output (`4`) on stdout, exit code `0`, stderr empty. Auth (the file-based
`~/.claude/.credentials.json`, read via the `--ro-bind / /` root — no separate mount needed since
credential reads don't require write access) survived confinement and the Anthropic API was
reached successfully.

The same run re-confirmed both D-03 denials still hold with the fix in place:

```
=== (a2) CONFINED WRITE INSIDE project_root (sanity) ===
INSIDE_WRITE_EXIT=0
-rw-r--r-- 1 root root 10 <ts> /workspace/project/inside_test.txt

=== (b) OUT-OF-ROOT WRITE DENIAL (target /root, not bound writable) ===
OUTSIDE_WRITE_EXIT=1
bash: line 1: /root/outside_test.txt: Read-only file system
ls: cannot access '/root/outside_test.txt': No such file or directory

=== (c) SSH READ DENIAL (tmpfs shadow of ~/.ssh) ===
cat: /root/.ssh/id_rsa_decoy: No such file or directory
SSH_READ_EXIT=1
```

- **Out-of-root write:** denied. Errno shape: EROFS ("Read-only file system"), same shape the
  23-spike captured from bwrap's `--ro-bind` mount-namespace layer (Section 2, Check (b) there).
  File confirmed absent afterward.
- **`~/.ssh` read:** denied. The decoy key planted at `/root/.ssh/id_rsa_decoy` (outside
  confinement, before the bwrap invocation) is invisible inside confinement — the `--tmpfs
  <home>/.ssh` mount shadows the real directory entirely, producing "No such file or directory"
  rather than a permission error, which is the expected shape for a tmpfs shadow (not a Landlock
  read-deny rule in this argv-only probe — Landlock is a separate, RUNG-1 layer `_wrap_linux`
  applies via the `--apply-landlock` shim, not exercised by this direct-argv probe per the Task-2
  action's scope).

## 6. DECISION

**FIX-APPLIED.** The exact shipped `build_linux_bwrap_args` argv, as originally written, failed
confined `claude --print` for a filesystem-write reason (EROFS on its own `/tmp` scratch dir). Per
the D-02 verify-first gate, a minimal bound-writable `/tmp` (`--tmpfs /tmp`) was added — nothing
broader (no `--ro-bind / /` removal, no bind of the real host `/tmp`, no writable `$HOME`) — and
the container probe was re-run to confirm: confined `claude --print` now succeeds (exit 0, real
output), and both D-03 denials (out-of-root write, `~/.ssh` read) still hold with the fix in place.
`flowstate/sandbox.py::build_linux_bwrap_args` now ships with this fix; the golden test in
`tests/test_sandbox.py` was updated to match and passes (73/73 in `tests/test_sandbox.py`).

## 7. WR-03 caveats — both closed

`23-SPIKE-LINUX.md` Section 5 recorded two production-shape gaps between that spike's probe and
the shipped code. Both are closed by this re-probe:

1. **Writable HOME** (23-spike used `--setenv HOME /tmp/chome`). **Closed**: the shipped
   `build_linux_bwrap_args` was re-probed with `$HOME` genuinely read-only under `--ro-bind / /`
   (no `--setenv HOME` shortcut anywhere in this probe). It failed for a *different*, narrower
   reason than a writable-HOME need (`/tmp` scratch, not `$HOME` itself) — confirming `$HOME`
   read-only is fine as-is; only `/tmp` needed a writable mount, which is now shipped.
2. **File-path credential** (23-spike used `CLAUDE_CODE_OAUTH_TOKEN` via `--env-file`). **Closed**:
   this re-probe used the FILE-based `~/.claude/.credentials.json` (0600, `bridge.py`'s real
   default), mounted read-only into the container, and confirmed a confined `claude --print`
   reads it successfully through the `--ro-bind / /` root and authenticates (exit 0, real output).

## 8. VERDICT

**FIX-APPLIED.** Linux `confine` now ships `build_linux_bwrap_args` with the minimal writable-`/tmp`
scratch mount added and re-verified. The exact shipped argv (post-fix) + the real file-based
credential preserve `claude` auth end-to-end; out-of-root writes and `~/.ssh` reads remain denied
under the same profile. Both `23-SPIKE-LINUX.md` WR-03 caveats are closed. No credential value was
committed anywhere in this repo at any point in this probe.
