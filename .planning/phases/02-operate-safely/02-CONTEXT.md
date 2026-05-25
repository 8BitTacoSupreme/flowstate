# Phase 2: Operate Safely - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Source:** User-authored spec inline during /gsd:new-project (no separate discuss-phase round)

<domain>
## Phase Boundary

Phase 2 delivers the **"operate this thing safely over time"** surface for FlowState — borrowed from ECC patterns (`affaan-m/ECC`) and adapted to FlowState's Python/Click/Pydantic/EventBus shape.

The phase has **four parallel-able workstreams** plus one sequencing constraint:

```
  ┌─ INST (install manifest)         ──┐
  │       ↓ (DOCT depends on INST)     │
  ├─ DOCT (doctor + repair)            ├─ all converge in Phase 2
  ├─ STAT (status --markdown)          │
  └─ HOOK (env-var handler gating)   ──┘
```

Phase 1 already landed (`b38bbd6`) — the v2 pivot is committed, version is 0.3.0, tests are green at 90.79%. This phase builds on a clean baseline.

**Out of scope for this phase** (deferred to v2 milestones — see REQUIREMENTS.md):
- Declarative `hooks.json` per-project hook config — `@handler` decorator is cleaner now
- Continuous-learning / auto-instinct extraction — ECC v1.4.1 had silent content-loss; defer
- Cross-harness packaging (Codex / OpenCode / Cursor) — multiplies install paths
- Formal eval/grading harness with pass@k — premature without run history
- Rust control-plane rewrite — solo-maintainer cautionary tale from ECC's `ecc2/`
- GUI dashboard (Tkinter / Electron) — CLI + Rich is on-brand
- Semantic embeddings on top of FTS5 — current scale doesn't warrant a vector DB
- Paid tier / hosted SaaS / GitHub App — different business model

</domain>

<decisions>
## Implementation Decisions

### INST — Install Manifest

**INST-01: Manifest schema on `FlowStateModel`**
- Add `install_manifest: list[InstallEntry]` field to `flowstate/state.py`
- `InstallEntry` is a new Pydantic model with: `path: str` (relative to root), `owner: str` (which init step wrote it — e.g. `"interview"`, `"context"`, `"memory"`, `"research_adapter"`), `kind: Literal["config", "context", "memory", "research", "artifact"]`, `created_at: datetime`, `checksum: str | None` (sha256 of file contents at write time; None for memory.db since it mutates)
- State version bumps to `0.3.0` (matches package version); migration adds the field with empty list as default

**INST-02: `flowstate init` populates the manifest**
- After each file write in the pipeline, the writer appends to `state.install_manifest`
- Backfill path: if loading a pre-manifest `flowstate.json`, scan `.planning/` + `research/` + `memory.db` + `flowstate.json` itself on first load and synthesize manifest entries from what's actually on disk (best-effort owner detection)
- The manifest is part of `flowstate.json` itself, so it's persisted with normal state saves

**INST-03: `flowstate fresh` uses the manifest, not `_FRESH_TARGETS`**
- Replace the hardcoded `_FRESH_TARGETS` list in `flowstate/cli.py` with a manifest read
- Files **in** the manifest → removed (only these)
- Files **not in** the manifest but in `.planning/` / `research/` → reported as "orphaned" and **left in place** unless `--force` is passed
- Files in the manifest but missing from disk → silently skipped (already gone)
- Mutated files (checksum mismatch) → warn before removing, require confirmation unless `--yes`

### DOCT — Doctor / Repair

**DOCT-01: `flowstate doctor` (new Click command)**
- Pure Python, no LLM, exits non-zero when any check fails (so it composes in CI / pre-commit)
- Checks (each emits a structured `Diagnosis` dataclass with `name`, `severity` Literal["error", "warning", "info"], `message`, `fix_hint: str | None`):
  1. **Manifest integrity** — every file in `install_manifest` exists; checksums match where set
  2. **Memory schema** — `memory.db` exists, FTS5 virtual table + triggers present, schema_version matches expected
  3. **Root resolution** — `resolve_root()` returns a real directory; saved `~/.config/flowstate/config.toml` (if present) points somewhere real
  4. **Claude CLI** — `_find_claude()` from `flowstate/bridge.py` locates a binary OR `FLOWSTATE_CLAUDE_BIN` is set
  5. **Stale tool status** — any `ToolState` with `status=Running` and `updated_at > 24h` ago
  6. **Orphaned files** — files in `.planning/` / `research/` not in the manifest (info-level, not error)
- Output: Rich-formatted table with per-check status (✓ / ⚠ / ✗) + a summary line; exit code = number of errors

**DOCT-02: `flowstate repair` applies safe fixes**
- Reads doctor's diagnoses and applies fixes for the **safe subset**:
  - Missing context files → regenerate from `state.interview` via `flowstate.context.write_context_files`
  - Memory schema drift → recreate FTS5 virtual table and triggers (`CREATE TABLE IF NOT EXISTS`, idempotent)
  - Stale Running statuses → reset to `Blocked` with a marker
  - Manifest checksum mismatches after intentional regeneration → rewrite checksums
- **Destructive ops gated behind `--apply-destructive`**:
  - Delete orphans (files not in manifest)
  - Drop memory rows / truncate `memory.db`
- Without `--apply-destructive`, destructive findings are reported but skipped; doctor will still flag them next run

### STAT — Status Snapshot

**STAT-01: `flowstate status --markdown`**
- Add `--markdown` flag to the existing `status` command in `flowstate/cli.py`
- Renders the current Pydantic state as a markdown document with three sections:
  1. **Tool Status** — markdown table with columns: `Tool | Status | Started | Completed | Duration | Artifacts | Error`
  2. **Active Phase** — current phase number/name from `.planning/ROADMAP.md` (if exists) + state.phase fields
  3. **Memory Stats** — entry count by `MemoryKind`, total memory.db size on disk, last entry timestamp
- Without `--markdown`, the existing Rich table output is preserved (backward compat)

**STAT-02: `flowstate status --markdown --write [path]`**
- New `--write` option taking an optional path argument (default: `status.md` in cwd)
- Writes the rendered markdown to the file; stdout prints a one-line confirmation with the absolute path
- Useful for cross-session handoff (paste the file into a chat / commit it / `cat` it from another terminal)

### HOOK — Hook Env-Gating

**HOOK-01: `FLOWSTATE_HANDLERS` env var profile gate**
- The env var must be **read at handler-registration time** (i.e., the env value in effect when each `@handler` decorator fires determines whether that handler registers). The exact mechanism — module-level cached constant vs. per-call lookup vs. helper function — is implementer's discretion. Per-call lookup is preferred because it's straightforward to monkeypatch in tests.
- Three profiles: `minimal` | `standard` | `unset = standard` | `strict`
- Extend the existing `@handler` decorator (in `flowstate/events/handler.py`) with a `profile: Literal["minimal", "standard", "strict"]` kwarg (default `"standard"`)
- At register time, if the handler's profile is stricter than the current env profile, skip registration (log an info-level message naming the skipped handler)
- Profile ordering: `minimal < standard < strict`
- Default mappings:
  - `memory_handlers.*` → `minimal` (always registered)
  - existing event-bus handlers → `standard`
  - (room for future audit handlers at `strict`)

**HOOK-02: `FLOWSTATE_DISABLED_HANDLERS` env var (comma-separated names)**
- Read alongside `FLOWSTATE_HANDLERS` at module-import time
- Comma-separated handler name list (e.g. `FLOWSTATE_DISABLED_HANDLERS=memory_step_completed,audit_log`)
- **Takes precedence over `FLOWSTATE_HANDLERS`** — a handler in the disabled list is skipped regardless of profile
- Whitespace around commas tolerated; empty strings ignored

### Claude's Discretion

- **InstallEntry checksum algorithm** — implementer picks sha256 unless there's a reason to use blake2b
- **doctor output format** — Rich table is the expectation but specific column ordering, color choices, etc. up to implementer
- **status --markdown table column order** — sensible defaults; can match existing Rich table or restructure for markdown readability
- **Where the FLOWSTATE_HANDLERS env read happens precisely** — registry.py module-init, or a `_load_profile()` helper called once; implementer's call
- **Memory-stats query approach** — direct SQL via `MemoryStore` or aggregate helpers; whichever is cleaner

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Architecture
- `.planning/codebase/ARCHITECTURE.md` — pattern overview, layers (CLI, State, Orchestrator, Adapters, Bridge, Memory, Events, Config, Launcher), data flow, key abstractions
- `.planning/codebase/STRUCTURE.md` — directory layout under `flowstate/` and `tests/`
- `.planning/codebase/CONVENTIONS.md` — code style, naming, error handling, typing usage
- `.planning/codebase/TESTING.md` — pytest setup, fixture patterns, coverage config
- `.planning/codebase/CONCERNS.md` — known fragile areas (now updated post-pivot, but still authoritative on the FTS5/subprocess concern shape)

### Existing Code (must be read before touching adjacent code)
- `flowstate/state.py` — Pydantic `FlowStateModel`, `ToolState`, `InterviewAnswers`, `ProjectPreferences`; load/save/migrate functions — **INST-01 extends this**
- `flowstate/cli.py` — all Click commands; new commands (`doctor`, `repair`) must follow the same `_root_was_explicit()` + `resolve_root()` pattern landed in Phase 1
- `flowstate/config.py` — `resolve_root()` precedence reference for new commands
- `flowstate/events/registry.py` — handler registration mechanism — **HOOK-01/02 extends this**
- `flowstate/events/handler.py` — `@handler` decorator — **HOOK-01 extends this with `profile=` kwarg**
- `flowstate/memory_handlers.py` — concrete handler examples; use these as the "minimal profile" baseline
- `flowstate/memory.py` — `MemoryStore`, schema setup, `_sanitize_fts_query()` — **DOCT-01 schema check reads this**
- `flowstate/context.py` — `write_context_files()` — **DOCT-02 calls this to regenerate**
- `flowstate/bridge.py` — `_find_claude()` — **DOCT-01 reuses this**
- `flowstate/discipline.py` — model for a pure-Python audit-style command; `doctor` mirrors this shape

### Project Standards
- `pyproject.toml` — coverage floor 80%, ruff config, dependency pins (no new deps in this phase)
- `.pre-commit-config.yaml` — hooks that run pre-push; tests must pass these
- `CLAUDE.md` (project root) — project context summary
- `.claude/CLAUDE.md` — project-instructions header

### Reference Material
- `affaan-m/ECC` README sections on `ECC_HOOK_PROFILE`, install manifest / state tracking, and `status --markdown` — these are the patterns being adapted; do NOT copy ECC code (different language, different scope) but the *behavior contracts* should be familiar

</canonical_refs>

<specifics>
## Specific Ideas

**INST-01 — Pydantic model addition:**
```python
class InstallEntry(BaseModel):
    path: str                                   # relative to project root
    owner: str                                  # "interview" | "context" | "memory" | tool name
    kind: Literal["config", "context", "memory", "research", "artifact"]
    created_at: datetime
    checksum: str | None = None                 # sha256; None for mutable files like memory.db

class FlowStateModel(BaseModel):
    # ... existing fields ...
    install_manifest: list[InstallEntry] = Field(default_factory=list)
```

**INST-03 — `fresh` rewrite skeleton:**

NOTE: `flowstate.state.load_state(root)` has no `missing_ok` parameter and will raise `FileNotFoundError` (or similar) if `flowstate.json` doesn't exist. The `fresh` command must guard against this — if there's no state file, there's no manifest to consult, so behave as if the manifest is empty.

```python
def fresh(root: Path | None, yes: bool, force: bool):
    root = resolve_root(root, option_was_explicit=_root_was_explicit())

    # Guard: missing state → empty manifest (fresh project, nothing to do via manifest)
    state_path = root / "flowstate.json"
    if state_path.exists():
        state = load_state(root)
        manifest = state.install_manifest
    else:
        manifest = []

    manifest_paths = {root / e.path for e in manifest}

    # Files we own (manifest) — only these are removed by default
    to_remove = [p for p in manifest_paths if p.exists()]
    # Files we don't own (orphans) — left in place unless --force
    orphans = _scan_planning_and_research(root) - manifest_paths
    if force:
        to_remove.extend(orphans)
    else:
        # report orphans, leave in place
        ...
```

**DOCT-01 — `Diagnosis` dataclass:**
```python
@dataclass(frozen=True)
class Diagnosis:
    name: str                                   # "manifest_integrity" | "memory_schema" | ...
    severity: Literal["error", "warning", "info"]
    message: str
    fix_hint: str | None = None
```

**STAT-01 — markdown layout sketch:**
```markdown
# FlowState Status — {project_root}

**Generated:** {ISO8601 timestamp}
**Version:** {flowstate version}

## Tools

| Tool | Status | Started | Completed | Duration | Artifacts | Error |
|------|--------|---------|-----------|----------|-----------|-------|
| research | Completed | 2026-05-25T12:34Z | 2026-05-25T12:36Z | 2m | research/report.md | — |
...

## Active Phase

**Phase 2: Operate Safely** (from .planning/ROADMAP.md)
Progress: 3/9 requirements complete

## Memory

| Kind | Count |
|------|-------|
| research | 42 |
| strategy | 8 |
| decision | 15 |
| tool_run | 3 |
| insight | 12 |

**Total entries:** 80 · **DB size:** 1.2 MB · **Last entry:** 2026-05-25T12:36Z
```

**HOOK-01 — registry.py shape:**
```python
_PROFILE_ORDER = {"minimal": 0, "standard": 1, "strict": 2}

def _current_profile() -> int:
    raw = os.environ.get("FLOWSTATE_HANDLERS", "standard").lower()
    return _PROFILE_ORDER.get(raw, _PROFILE_ORDER["standard"])

def _disabled_names() -> set[str]:
    raw = os.environ.get("FLOWSTATE_DISABLED_HANDLERS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}
```

</specifics>

<deferred>
## Deferred Ideas

(From the v2 requirements + Out of Scope sections of REQUIREMENTS.md — explicitly NOT part of Phase 2)

- **Declarative `hooks.json`** — keep `@handler` decorator path; revisit if users need per-project hook config
- **Auto-instinct extraction** — manual memory promotion is fine for now; ECC's silent-loss bugs argue against rushing this
- **Distribution (PyPI / Homebrew / Flox catalog)** — v2 milestone work
- **Cross-harness adapters (Codex / OpenCode / Cursor)** — v2 milestone work
- **Eval / pass@k harness** — v2 milestone work, needs run-history corpus first

</deferred>

---

*Phase: 02-operate-safely*
*Context gathered: 2026-05-25 from user-authored spec during /gsd:new-project*
