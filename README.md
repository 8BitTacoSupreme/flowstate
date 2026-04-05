# FlowState — The GrandSlam Orchestrator

FlowState is a CLI-first orchestrator that unifies four agentic frameworks (the "Agentic Quadruple") into a single pipeline, eliminating tool fatigue and managing handoffs automatically.

## The GrandSlam

| Tool | Role | What it does |
|------|------|-------------|
| **Autoresearch** | Intelligence | Deep-dives into docs, GitHub issues, and papers to find the best approach |
| **Gstack** | Strategy | Pressure-tests ideas using the Garry Tan /office-hours framework |
| **GSD** | Management | Maintains roadmaps and project state for velocity tracking |
| **Superpowers** | Discipline | Executes code via a Worktree → Plan → TDD → Execute loop |

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  flowstate CLI                   │
│         init · status · run · check              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│               Orchestrator                       │
│  Sequences the 4 tools, manages state,           │
│  handles failures and fallbacks                  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              ClaudeBridge                        │
│  Wraps `claude --print` for non-interactive      │
│  invocation with system prompts, tool            │
│  permissions, and timeout management             │
└──┬──────────┬──────────┬──────────┬─────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐
│Auto- │ │Gstack│ │ GSD  │ │Super-    │
│rsrch │ │      │ │      │ │powers    │
└──┬───┘ └──┬───┘ └──┬───┘ └──┬───────┘
   │        │        │        │
   ▼        ▼        ▼        ▼
 claude   claude   /gsd:*   claude
 --print  --print  skills   --print
```

**State flow:** All pipeline state is persisted to `flowstate.json` — a Pydantic-validated file tracking tool status (Ready/Running/Completed/Blocked), artifact paths, and user preferences.

## Prerequisites

- **Python 3.12+**
- **Claude Code CLI** (v2.0+) — [install guide](https://docs.anthropic.com/en/docs/claude-code/overview)
- **GSD** (optional, for Management phase) — [github.com/gsd-build/gsd-2](https://github.com/gsd-build/gsd-2)

Claude Code requires an active Anthropic account. Use of the `claude` CLI is subject to [Anthropic's Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms).

## Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USER/frameworx.git
cd frameworx

# Create a virtual environment (Python 3.12+ required)
python3.13 -m venv .venv
source .venv/bin/activate

# Install FlowState
pip install -e .
```

Verify the install:

```bash
flowstate --version
# flowstate, version 0.1.0

flowstate check
# claude CLI found: /Users/you/.local/bin/claude
# Timeout: 600s | Max turns: 10
```

## Usage

### 1. Initialize a project

```bash
flowstate init
```

This runs the full GrandSlam pipeline:

1. **Interview** — prompts you for research focus, core problem, milestones, architecture preferences
2. **Intelligence** — runs Autoresearch via Claude to produce `research/report.md`
3. **Strategy** — runs office-hours pressure-test to produce `research/strategy.md`
4. **Management** — invokes `/gsd:new-project` to create `.planning/ROADMAP.md`
5. **Discipline** — sets up git hooks, test infra, and coding standards

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

Outputs a Rich table showing each tool's status, artifacts, and errors:

```
┌──────────────────────────────────────────────────────┐
│                   FlowState Status                    │
├──────────────┬──────────────┬───────────┬────────────┤
│ Tool         │ Phase        │ Status    │ Artifacts  │
├──────────────┼──────────────┼───────────┼────────────┤
│ autoresearch │ Intelligence │ completed │ research/… │
│ gstack       │ Strategy     │ completed │ research/… │
│ gsd          │ Management   │ completed │ .planning… │
│ superpowers  │ Discipline   │ completed │ ---        │
└──────────────┴──────────────┴───────────┴────────────┘
```

### 3. Run a phase

```bash
flowstate run 1
```

Plans and executes GSD phase 1. If the phase label contains hardening keywords (stabilize, optimize, etc.), FlowState automatically creates a git worktree branch to preserve main-line stability.

### 4. Verify the bridge

```bash
flowstate check
```

Confirms the `claude` CLI is detected and shows configuration.

## Project structure

```
frameworx/
├── flowstate/
│   ├── cli.py              # Click CLI entrypoints
│   ├── interview.py        # Rich-powered intake interview
│   ├── orchestrator.py     # Pipeline sequencing and status display
│   ├── state.py            # Pydantic models + flowstate.json persistence
│   ├── bridge.py           # ClaudeBridge — claude CLI wrapper
│   └── tools/
│       ├── base.py         # ToolAdapter base class + ToolResult
│       ├── autoresearch.py # Intelligence adapter
│       ├── gstack.py       # Strategy adapter
│       ├── gsd_adapter.py  # Management adapter (real /gsd:* skills)
│       └── superpowers.py  # Discipline adapter (worktree mgmt)
├── tests/                  # 26 tests
├── research/               # Generated research artifacts
├── flowstate.json          # Pipeline state (gitignored)
├── pyproject.toml
├── LICENSE                 # Apache 2.0
└── NOTICE                  # Third-party attributions
```

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

**ClaudeBridge** is the key abstraction. It wraps `claude --print` (non-interactive mode) with:
- `--system-prompt` for persona injection (researcher, advisor, engineer)
- `--allowedTools` for scoped tool permissions per adapter
- `--max-turns` to bound agentic execution
- `CLAUDECODE` env var removal to allow subprocess invocation from within a Claude session

Each tool adapter inherits from `ToolAdapter` and implements its domain logic:
- **Dry-run mode**: returns mock output and writes template artifacts
- **Live mode**: constructs a structured prompt, sends it through ClaudeBridge, and captures the output

The orchestrator runs the four adapters in sequence, persisting state to `flowstate.json` after each step. If a tool fails, it's marked `BLOCKED` and the pipeline continues.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

FlowState calls external tools via subprocess and does not bundle their code. Users are responsible for complying with the terms of service for any tools they use through FlowState, including [Anthropic's Commercial Terms](https://www.anthropic.com/legal/commercial-terms) for Claude Code.
