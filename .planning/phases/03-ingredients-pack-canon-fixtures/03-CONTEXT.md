# Phase 3: Ingredients — Pack, Canon, Fixtures - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Source:** Milestone v0.4.0 plan + codebase exploration (auto mode)

<domain>
## Phase Boundary

Build the THREE new context sources as independent, testable artifacts/constants
BEFORE any composition layer (Phase 4 wires them together). In scope:
- **Repomix pack** (PACK-01/02/03): `flowstate pack` CLI command + staleness repack + repomix-MCP registration
- **Karpathy canon** (CANON-01): bridge system-prompt constant
- **ECC-modeled eval fixtures** (FIX-01/02): fixture format + init scaffolding
- **Repomix CLAUDE.md guidance** (DX-02): own + generated docs

OUT of scope this phase: the `build_context_prefix()` assembler, fit/compress/omit
logic, cache lean-in (all Phase 4); `flowstate kickoff` + `status:` frontmatter (Phase 5).
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Repomix wiring (PACK)
- **Both CLI + MCP.** FlowState shells out to the `repomix` CLI to PRODUCE the pack it will
  later inject (pure-Python subprocess, no bridge MCP dependency); separately registers
  repomix-MCP in the project `.mcp.json` so spawned `claude --print` agents can grep the pack
  as retrieval-on-top.
- **Locator pattern:** mirror `flowstate/bridge.py::_find_claude()` — locate `repomix` via PATH
  then `FLOWSTATE_REPOMIX_BIN` env override. Graceful failure (clear message + non-zero exit)
  when absent. Repomix is an external Node CLI/MCP like `claude` — NOT a Python dependency.
- **Pack artifact path:** `.planning/codebase/repomix-pack.xml` (xml is repomix default; reuse
  the existing `.planning/codebase/` dir that map-codebase already populates).
- **Staleness (PACK-02):** repack only if any tracked source file is newer than the pack's
  `created_at` recorded on `install_manifest`; else reuse. Reuse the InstallEntry checksum/
  created_at machinery from v0.3.

### Canon (CANON-01)
- Karpathy's 4 guidelines (Think Before Coding / Simplicity First / Surgical Changes /
  Goal-Driven Execution) ship as a `CANON` string constant in `flowstate/bridge.py`.
- Prepended to EVERY `claude --print` system prompt as the first (most stable) layer.
- Suppressible via `BridgeConfig.inject_canon: bool = True`.
- Source text already exists verbatim in /Users/jhogan/CLAUDE.md §1–4 — lift it; do not invent.

### Eval fixtures (FIX)
- Format modeled on ECC's `examples/evaluator-rag-prototype/scenario.json`:
  `retrieval_questions[]`, `acceptance_gates[]`, `forbidden_actions[]` + a system-contract
  section + ≥1 few-shot exemplar.
- Stored under `.planning/fixtures/` as a pack-able artifact (so Phase 4 can fold it into the prefix).
- `flowstate init` (and later `kickoff`) scaffolds a STARTER fixture derived from
  `state.interview` answers; register it on `install_manifest`.

### DX-02
- Add "consult the Repomix pack instead of crawling source every wave" guidance to BOTH:
  FlowState's own `/Users/jhogan/frameworx/.claude/CLAUDE.md`, AND the
  `generate_claude_md()` template in `flowstate/context.py` (for downstream projects).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bridge / canon seam
- `flowstate/bridge.py` — `ClaudeBridge.run()` (~L95-104), system-prompt assembly (~L132-162),
  `BridgeConfig` dataclass (~L45-53), `_find_claude()` locator (the pattern to mirror for repomix).

### Pack seam
- `flowstate/state.py` — `InstallEntry` model (`kind` is a `Literal[...]`; extend with `pack`/`fixture`),
  `install_manifest` field, checksum/created_at helpers.
- `flowstate/cli.py` — Click command structure (`main` group, `--root` resolution via `config.resolve_root`,
  `doctor`/`fresh` as analog pure-Python commands). New `pack` command goes here.
- `flowstate/context.py` — `write_context_files()` (~L171) registers files on the manifest; analog for
  registering the pack + fixture + `.mcp.json`. `generate_claude_md()` (~L114-140) for DX-02.

### Fixtures
- ECC reference shape: `examples/evaluator-rag-prototype/scenario.json` (retrieval_questions /
  acceptance_gates / forbidden_actions).

### Interview / init
- `flowstate/interview.py` (`run_interview()` ~L60-112), `flowstate/state.py::InterviewAnswers` (~L28-34)
  — fixture scaffolding derives from these answers.

### Tests (analogs to copy)
- `tests/test_doctor.py`, `tests/test_repair.py` — pure-Python command tests.
- `tests/test_cli.py` — `CliRunner` pattern + `healthy_install` fixture in `tests/conftest.py`
  (monkeypatch subprocess for repomix; never shell out in tests).
- `tests/test_install_manifest.py` — InstallEntry/manifest tests.
- `tests/test_context.py` — context-generation (offline) tests.
- `tests/test_bridge.py` — bridge tests (canon injection + `inject_canon=False` suppression).
</canonical_refs>

<specifics>
## Specific Ideas

- `flowstate pack` must be CliRunner-testable: factor the repomix subprocess call behind a
  function in a new `flowstate/pack.py` (locator + `run_pack(root, *, compress=False) -> Path`
  + staleness check) so tests monkeypatch it like the bridge is monkeypatched.
- Coverage ≥80% enforced; pre-commit runs ruff + pytest. No new Python runtime deps.
- Reuse the ~4-chars/token estimate already in `memory.py::get_context` if any token math is needed
  (though fit logic is Phase 4, not here).
</specifics>

<deferred>
## Deferred Ideas

- `build_context_prefix()` + fit/compress/omit + cache lean-in → Phase 4 (CAG-01..03).
- `flowstate kickoff` + enhanced interview + `status:` SUMMARY frontmatter → Phase 5 (KICK/DX-01).
</deferred>

---

*Phase: 03-ingredients-pack-canon-fixtures*
*Context gathered: 2026-06-06 via milestone plan + exploration (auto mode)*
