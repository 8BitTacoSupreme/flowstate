# FlowState — Context for Session Resume

## What This Is

FlowState is a Python CLI orchestrator ("The GrandSlam Orchestrator") that unifies four agentic frameworks into a single pipeline:

1. **Autoresearch** (Intelligence) — research via Claude CLI
2. **Gstack** (Strategy) — Garry Tan office-hours pressure-test
3. **GSD** (Management) — roadmap/state via `/gsd:*` Claude Code skills
4. **Superpowers** (Discipline) — worktree-based TDD execution

## Repo

- **Remote**: https://github.com/8BitTacoSupreme/flowstate
- **Branch**: `main`
- **Local path**: `/Users/jhogan/frameworx`
- **License**: Apache 2.0

## What's Built (Phases 1-2 complete)

### Phase 1 — Intake & Orchestration Engine
- Pydantic state model (`flowstate.json`) tracking tool status, artifacts, preferences
- Rich-powered CLI interview (4 sections: research/strategy/management/discipline)
- Sequential pipeline orchestrator for the Agentic Quadruple
- Tool adapters with dry-run mock mode
- CLI: `flowstate init`, `flowstate status`

### Phase 2 — ClaudeBridge & Real CLI Integrations
- `flowstate/bridge.py` — wraps `claude --print` for non-interactive invocation
  - System prompts, `--allowedTools`, `--max-turns`, timeout, `CLAUDECODE` env bypass
  - Auto-detects claude CLI on PATH or via `FLOWSTATE_CLAUDE_BIN`
- All 4 adapters rewritten to use structured prompts through the bridge
  - Autoresearch: research system prompt + WebSearch/WebFetch tools
  - Gstack: advisor persona + `flox:flox-environments` skill
  - GSD: invokes real `/gsd:new-project`, `/gsd:plan-phase`, `/gsd:execute-phase`
  - Superpowers: init prompt + `git worktree add` for hardening phases
- CLI: added `flowstate run <phase>`, `flowstate check`
- Orchestrator falls back to dry-run when claude CLI missing

### Flox Environment
- `flox activate` provides: Python 3.13, Node 24, git, jq, ripgrep
- Auto-installs Claude Code CLI, Context7 MCP, Exa MCP (cached in `.flox/cache/`)
- Auto-creates `.venv`, installs FlowState, configures `.claude/settings.json` with MCP servers
- `.env` support for API keys (sourced on activate)

## File Map

```
flowstate/
├── .flox/env/manifest.toml    # Flox environment definition
├── .claude/settings.json      # MCP server config (Context7, Exa)
├── .env.example               # API key template
├── flowstate/
│   ├── cli.py                 # Click CLI: init, status, run, check
│   ├── interview.py           # Rich interview (4 sections)
│   ├── orchestrator.py        # Pipeline sequencer + status display
│   ├── state.py               # Pydantic models + flowstate.json I/O
│   ├── bridge.py              # ClaudeBridge (claude --print wrapper)
│   └── tools/
│       ├── base.py            # ToolAdapter base + ToolResult dataclass
│       ├── autoresearch.py    # Intelligence adapter
│       ├── gstack.py          # Strategy adapter (init_stack + office_hours)
│       ├── gsd_adapter.py     # Management adapter (new_project, plan/execute_phase)
│       └── superpowers.py     # Discipline adapter (init_repo, worktree, should_branch)
├── tests/                     # 26 tests, all passing (dry-run, no claude needed)
│   ├── test_bridge.py
│   ├── test_interview.py
│   ├── test_orchestrator.py
│   ├── test_state.py
│   └── test_tools.py
├── pyproject.toml             # Python package config (Apache-2.0, click/pydantic/rich)
├── LICENSE                    # Apache 2.0
├── NOTICE                     # Third-party attributions
└── README.md                  # Full docs with architecture diagram
```

## Commit History

```
4e27227 feat: add .env support for API keys
309af46 feat: add Flox environment with Claude Code and MCP servers
4b6aafb fix: correct repo URL and directory name in README
8268e3f docs: add Apache 2.0 license, NOTICE, and README
21af63e feat: Phase 2 — ClaudeBridge and real CLI integrations
1b3e3a0 feat: initialize FlowState Phase 1 — intake and orchestration engine
9a0a044 Initial commit
```

## Key Design Decisions

- **ClaudeBridge** is the core abstraction — all tools go through `claude --print`
- Prompt is a **positional arg** to claude CLI (not `--prompt`)
- `CLAUDECODE` env var must be unset for subprocess invocation from within Claude sessions
- `--allowedTools` accepts comma-separated tool names
- GSD skills invoked as `/<skill-name>` prompts (e.g., `/gsd:new-project --auto`)
- Worktree auto-branching triggers on hardening keywords: harden, stabilize, polish, optimize, scale
- State persisted after every pipeline step (crash-resilient)

## What's Next (Phase 3 candidates)

- **Live test** — run `flowstate init` without `--dry-run` end-to-end
- **Feedback loop** — verify → iterate cycle between GSD phases
- **FastAPI backend** — expose orchestrator as an API
- **Phase chaining** — `flowstate run --all` to sequence all phases
- **Progress reporting** — richer status with timing, token usage estimates

## Dev Commands

```bash
flox activate                          # full environment
source .venv/bin/activate              # just Python (fallback)
python -m pytest tests/ -v             # run tests (26 passing)
flowstate init --dry-run               # test pipeline
flowstate check                        # verify claude bridge
flowstate status                       # show tool state
```
