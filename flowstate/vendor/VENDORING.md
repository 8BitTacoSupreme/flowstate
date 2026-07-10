# Vendoring GSD into FlowState

This is the **single canonical procedure** for producing `flowstate/vendor/gsd/`. The GSD refresh
path (Plan 15-04) MUST reuse this exact procedure so a refresh cannot diverge from the original
snapshot.

FlowState bundles a lean, full-parity [GSD](https://github.com/gsd-build/get-shit-done)
distribution (`get-shit-done-cc`, MIT © 2025 Lex Christopherson) so `gsd-sdk` works with zero
separate install. GSD is vendored as **data only** — no vendored file is executed at build,
install, or test time except the read-only `gsd-sdk query` invokability check below.

## Pinned version

- npm package: `get-shit-done-cc`
- version: **`1.42.3`** (pinned; no moving tags)
- provenance recorded in `gsd/VERSION` + `gsd/package-lock.json` (lockfileVersion 3)

## Procedure

1. **Clean scratch dir** — never install into the repo tree:

   ```sh
   mkdir -p /tmp/gsd-vendor && cd /tmp/gsd-vendor
   printf '{"name":"gsd-vendor-scratch","version":"1.0.0","private":true}\n' > package.json
   ```

2. **Lean install** — `--omit=optional` drops the ~197M platform `claude` binary;
   `--omit=dev` drops dev deps. Result ≈ 51M, ~100 production packages:

   ```sh
   npm install get-shit-done-cc@1.42.3 --omit=optional --omit=dev --no-audit --no-fund
   ```

3. **Enforce the platform binary is absent** (it is redundant with the user's own `claude`
   prerequisite, platform-locked, and ~400× over the large-file hook). Both must be empty:

   ```sh
   find node_modules -type f -size +10M                 # must print nothing
   find node_modules -type d -name 'claude-agent-sdk-*'  # must print nothing
   ```

   If a platform dir appears on some environment despite `--omit=optional`, delete it and re-verify.

4. **Vendor the tree** into the repo:

   ```sh
   DEST=flowstate/vendor/gsd
   rm -rf "$DEST/node_modules"
   cp -R node_modules            "$DEST/node_modules"
   cp package-lock.json          "$DEST/package-lock.json"
   cp node_modules/get-shit-done-cc/LICENSE "$DEST/LICENSE"   # verbatim
   ```

   Then update `$DEST/VERSION` (version + lockfile integrity) and this file's pin if the version
   changed.

5. **Invokability parity gate (authoritative)** — run from the repo root, against a project with
   `.planning/ROADMAP.md`. This proves full `gsd-sdk` parity with the platform binary absent:

   ```sh
   node flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js query roadmap.get-phase 15
   #   -> output contains "phase_name": "Bundle GSD"
   node flowstate/vendor/gsd/node_modules/get-shit-done-cc/bin/gsd-sdk.js query config-get commit_docs
   #   -> true
   ```

## Cross-platform note

No platform binary is vendored, so `gsd-sdk query` (the path GSD's skills use in 104 files) works
on **every** platform. Agent-session spawning — the only thing the omitted binary did — falls back
to the user's own `claude` on `PATH`, which FlowState already requires.

## Build/test/commit integration

The vendored tree is excluded from:

- the `check-added-large-files` pre-commit hook (`exclude: ^flowstate/vendor/`; global `--maxkb`
  unchanged) plus `trailing-whitespace` / `end-of-file-fixer` (keep JS/mjs byte-verbatim)
- pytest collection (root `conftest.py` `collect_ignore_glob`)
- coverage (`[tool.coverage.run] omit = [... "flowstate/vendor/*"]`)

…and force-included in the wheel (`[tool.hatch.build.targets.wheel] artifacts`) so it ships.

Third-party attributions: GSD's own `LICENSE` is captured verbatim at `gsd/LICENSE`; the ~100
bundled dependency packages carry their own LICENSE files under `gsd/node_modules/`, pointed to
from the repo-root `NOTICE`.
