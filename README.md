# FlowState — The Context Orchestrator

FlowState is a CLI-first orchestrator that prepares context files for agentic frameworks, runs targeted LLM research and strategy calls, and hands off to native Claude Code tools for execution.

## What FlowState Does

| Step | Role | What happens |
|------|------|-------------|
| **Context Generation** | Setup | Writes PROJECT.md, ROADMAP.md, CLAUDE.md, config.json, research brief — deterministic, <1s |
| **Research** | Intelligence | Split-topic `claude --print` calls (~30s/topic) producing `research/report.md` |
| **Strategy** | Strategy | Single pressure-test `claude --print` call (~75s) producing `research/strategy.md` |
| **Management** | GSD | Writes context files for GSD skills; phases run natively via `flowstate launch gsd <N>` |
| **Discipline** | Audit | Pure Python audit of git repo, test config, hooks — no LLM needed |

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   flowstate CLI                   │
│    init · status · launch · context · check       │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│                 Orchestrator                       │
│   5-step pipeline with state persistence           │
└──┬──────────┬──────────┬──────────┬──────────┬───┘
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
Context    Research   Strategy    GSD      Discipline
Generator  Adapter    Adapter   Adapter     Audit
(Python)   (bridge)   (bridge)  (context)  (Python)
   │          │          │          │          │
   ▼          ▼          ▼          ▼          ▼
 5 files   claude     claude    .planning/  git/test
 written   --print    --print   files       checks
```

**State flow:** All pipeline state is persisted to `flowstate.json` — a Pydantic-validated file tracking tool status (Ready/Running/Completed/Blocked), artifact paths, context files, and user preferences.

## Prerequisites

- **[Flox](https://flox.dev)** (recommended) — handles everything below automatically
- **Python 3.12+**
- **Claude Code CLI** (v2.0+) — [install guide](https://docs.anthropic.com/en/docs/claude-code/overview)
- **GSD** (optional, for Management phase) — [github.com/gsd-build/gsd-2](https://github.com/gsd-build/gsd-2)

Claude Code requires an active Anthropic account. Use of the `claude` CLI is subject to [Anthropic's Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms).

## Installation

### Option A: Flox (recommended)

One command gives you Python, Node, Claude Code CLI, MCP servers (Context7, Exa), and FlowState — fully reproducible.

```bash
git clone https://github.com/8BitTacoSupreme/flowstate.git
cd flowstate
flox activate
```

On first activation, Flox automatically:
- Creates a Python venv and installs FlowState
- Installs Claude Code CLI via npm
- Installs Context7 and Exa MCP servers
- Configures `.claude/settings.json` with MCP server entries

Subsequent activations are instant (everything is cached).

### Option B: Manual (pip/venv)

```bash
git clone https://github.com/8BitTacoSupreme/flowstate.git
cd flowstate

python3.12 -m venv .venv   # or python3.13
source .venv/bin/activate
pip install -e .
```

You'll also need to install [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) separately.

### Verify

```bash
flowstate --version
# flowstate, version 0.2.0

flowstate check
# claude CLI found: /Users/you/.local/bin/claude
# Timeout: 300s | Max turns: 10
```

## Usage

### 1. Initialize a project

```bash
flowstate init
```

This runs the full pipeline:

1. **Interview** — prompts you for research focus, core problem, milestones, architecture preferences
2. **Context Generation** — writes 5 context files deterministically (<1s)
3. **Research** — splits topics and runs focused `claude --print` calls (~30s/topic)
4. **Strategy** — runs a single pressure-test call (~75s)
5. **Discipline Audit** — pure Python check of git repo, tests, hooks (<1s)
6. **Summary** — lists created files and next-step commands

To test the pipeline without calling real tools:

```bash
flowstate init --dry-run
```

To re-run the pipeline with existing interview answers:

```bash
flowstate init --skip-interview
```

### 2. Check status

```bash
flowstate status
```

Outputs a Rich table showing each tool's status, artifacts, and context files:

```
┌──────────────────────────────────────────────────────┐
│                   FlowState Status                    │
├──────────────┬──────────────┬───────────┬────────────┤
│ Tool         │ Phase        │ Status    │ Artifacts  │
├──────────────┼──────────────┼───────────┼────────────┤
│ research     │ Research     │ completed │ research/… │
│ strategy     │ Strategy     │ completed │ research/… │
│ gsd          │ Management   │ completed │ .planning… │
│ discipline   │ Discipline   │ completed │ ---        │
└──────────────┴──────────────┴───────────┴────────────┘
```

### 3. Launch native tools

```bash
flowstate launch gsd 1
# → cd /path/to/project && claude
# → /gsd:plan-phase 1
```

GSD phases run natively inside Claude Code sessions where they actually work. `flowstate launch` prints the exact commands.

### 4. Regenerate context files

```bash
flowstate context
```

Regenerates all 5 context files from current state without re-running the full pipeline.

### 5. Run a phase

```bash
flowstate run 1
```

Prints the native session command for executing a GSD phase.

### 6. Verify the bridge

```bash
flowstate check
```

Confirms the `claude` CLI is detected and shows configuration.

## Project structure

```
flowstate/
├── flowstate/
│   ├── cli.py              # Click CLI entrypoints
│   ├── interview.py        # Rich-powered intake interview
│   ├── orchestrator.py     # 5-step pipeline sequencing
│   ├── state.py            # Pydantic models + flowstate.json persistence
│   ├── bridge.py           # ClaudeBridge — claude CLI wrapper
│   ├── context.py          # Deterministic context file generator
│   ├── launcher.py         # Native session launch helpers
│   ├── discipline.py       # Pure Python project audit
│   ├── events/             # Event-driven infrastructure
│   └── tools/
│       ├── base.py         # ToolAdapter base class + ToolResult
│       ├── research.py     # Research adapter (split-topic)
│       ├── strategy.py     # Strategy adapter (pressure-test)
│       └── gsd_adapter.py  # Management adapter (context files)
├── tests/                  # 111 tests, 93% coverage
├── research/               # Generated research artifacts
├── flowstate.json          # Pipeline state (gitignored)
├── pyproject.toml
├── LICENSE                 # Apache 2.0
└── NOTICE                  # Third-party attributions
```

## Context files generated

`flowstate init` writes these files for downstream tools:

| File | Consumer | Content |
|------|----------|---------|
| `.planning/PROJECT.md` | GSD | Vision, problem, constraints, requirements |
| `.planning/ROADMAP.md` | GSD | Phases from milestones with acceptance criteria |
| `.planning/config.json` | GSD | Workflow preferences (mode, granularity) |
| `.claude/CLAUDE.md` | All tools | Project context, active tools, current phase |
| `research/brief.md` | Research adapter | Structured research questions from interview |

## Configuration

| Env var | Purpose |
|---------|---------|
| `FLOWSTATE_CLAUDE_BIN` | Override path to the `claude` binary |

FlowState auto-detects `claude` on your PATH and in common install locations (`~/.local/bin/claude`, `/usr/local/bin/claude`, `/opt/homebrew/bin/claude`).

## Running tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

All tests use dry-run mode and do not require the `claude` CLI.

## How it works (for contributors)

### Three layers

**Layer 1 — Context Generator** (`context.py`): Pure Python templates that transform interview answers into the files upstream tools consume. No LLM. No timeouts. Fully testable.

**Layer 2 — Targeted LLM Calls** (`research.py`, `strategy.py`): Keep `claude --print` for exactly two operations where LLM adds value:
- **Research** — one short call per topic (~30s each), merged into `research/report.md`
- **Strategy** — single pressure-test call (~75s), writes `research/strategy.md`

**Layer 3 — Session Launcher** (`launcher.py`): `flowstate launch` prints exact commands for native Claude Code execution. Tools run inside Claude Code where they actually work.

### ClaudeBridge

Wraps `claude --print` (non-interactive mode) with:
- `--system-prompt` for persona injection (researcher, advisor)
- `--allowedTools` for scoped tool permissions per adapter
- `--max-turns` to bound agentic execution
- `CLAUDECODE` env var removal to allow subprocess invocation from within a Claude session

### State persistence

The orchestrator persists state to `flowstate.json` after each step. If a tool fails, it's marked `BLOCKED` and the pipeline continues. State files from v0.1.0 are automatically migrated to v0.2.0 format.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

FlowState calls external tools via subprocess and does not bundle their code. Users are responsible for complying with the terms of service for any tools they use through FlowState, including [Anthropic's Commercial Terms](https://www.anthropic.com/legal/commercial-terms) for Claude Code.
