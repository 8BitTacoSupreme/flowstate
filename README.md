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
│                   flowstate CLI                  │
│  init · kickoff · status · run · launch · context│
│  memory · journal · gotchas · verify · pack      │
│  discipline · doctor · repair                    │
│  fresh · check · config                          │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────┐
│                 Orchestrator                       │
│   5-step pipeline with state persistence           │
│   EventBus emits StepCompleted / StepFailed        │
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
                      │
              ┌───────▼────────┐
              │  MemoryStore   │
              │  (SQLite FTS5) │
              │  memory.db     │
              └────────────────┘
```

**State flow:** All pipeline state is persisted to `flowstate.json` — a Pydantic-validated file tracking tool status (Ready/Running/Completed/Blocked), artifact paths, context files, and user preferences.

**Memory:** Research findings, strategy decisions, and failure context are stored in `memory.db` (SQLite FTS5, with optional `sqlite-vec` semantic retrieval) and automatically injected into subsequent pipeline runs. See [Persistent Memory](#persistent-memory) below.

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

# Optional: enable semantic memory retrieval (adds fastembed; downloads a ~130MB model on first use)
pip install -e ".[semantic]"
```

You'll also need to install [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) separately.

### Verify

```bash
flowstate --version
# flowstate, version 0.6.0

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

### 6. Query memory

```bash
# Search stored knowledge
flowstate memory search "kafka streams"

# Show counts by kind
flowstate memory stats

# Clear all memories (with confirmation)
flowstate memory clear
```

On each pipeline run, research findings, strategy assessments, and failure logs are automatically stored. Subsequent runs inject relevant prior knowledge into bridge prompts so research compounds over time. See [Persistent Memory](#persistent-memory) below.

### 7. Verify the bridge

```bash
flowstate check
```

Confirms the `claude` CLI is detected and shows configuration.

### 8. Other commands

Beyond the core pipeline, FlowState ships commands for fast scaffolding, the compounding loop, context packing, and operate-safely health:

| Command | Purpose |
|---------|---------|
| `flowstate kickoff` | Scaffold a project (interview + context files + pack) with **no** LLM pipeline |
| `flowstate journal` | List recent run-journal entries (the `## Since Last Run` deltas) newest-first |
| `flowstate gotchas` | List accumulated failure signals (the `## Gotchas` layer); `--prune` to trim |
| `flowstate verify` | Run fixture acceptance-gates against produced artifacts (CI-composable exit code) |
| `flowstate pack` | Generate/refresh the repomix codebase pack used by the CAG context layer |
| `flowstate discipline` | Live pure-Python audit — runs the project's tests, reads real git state, checks hook contents (the Discipline stage, standalone) |
| `flowstate doctor` | Pure-Python health checks (manifest, memory schema, root, claude CLI, orphans) |
| `flowstate repair` | Apply safe fixes for `doctor` findings (`--apply-destructive` gates risky ones) |
| `flowstate fresh` | Remove FlowState-owned files per the install manifest (orphans reported, not nuked) |
| `flowstate config` | Manage global configuration (e.g. default project root) |

Together, `journal` + `gotchas` + `verify` form the **compounding loop**: each run leaves a delta trail and structured failure signals that the next run reads first, so work compounds instead of repeating.

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
│   ├── memory.py           # SQLite FTS5 + optional sqlite-vec semantic memory store
│   ├── embeddings.py       # Lazy optional embedding provider ([semantic] extra)
│   ├── memory_handlers.py  # EventBus handlers for auto-storing results
│   ├── context_prefix.py   # Layered CAG context-prefix assembler
│   ├── gotchas.py          # Accumulated failure-signal layer
│   ├── journal.py          # Append-only run-delta journal
│   ├── verify.py           # Runnable fixture-gate verification
│   ├── pack.py             # repomix codebase-pack integration
│   ├── doctor.py           # Pure-Python health checks + repair
│   ├── events/             # Event-driven infrastructure
│   └── tools/
│       ├── base.py         # ToolAdapter base class + ToolResult
│       ├── research.py     # Research adapter (split-topic)
│       ├── strategy.py     # Strategy adapter (pressure-test)
│       └── gsd_adapter.py  # Management adapter (context files)
├── tests/                  # 985 tests, 92% coverage
├── bench/                  # research harness: grounding eval, RGB axes, arms, promptab/sysab A/B, tune_loop
├── research/               # Generated research artifacts
├── flowstate.json          # Pipeline state (gitignored)
├── memory.db               # Persistent memory (gitignored)
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

### Persistent memory

Each pipeline run stores research findings, strategy assessments, interview decisions, and failure logs in `memory.db` — a single SQLite file using FTS5 for full-text search with porter stemming.

**How it works:**

1. The orchestrator creates a `MemoryStore` and `EventBus` at pipeline start
2. Memory handlers listen for `StepCompleted` / `StepFailed` events
3. On completion, artifact files are split by `## ` headings and stored as individual memory entries
4. On failure, the error is stored as a `tool_run` memory for future reference
5. Before each bridge call, the adapter calls `get_memory_context(topic)` — if relevant prior knowledge exists, it's prepended to the prompt as a `## Prior Knowledge` section

**Memory kinds:** `research`, `strategy`, `decision`, `tool_run`, `insight`, `run`

**Search:** FTS5 with BM25 ranking by default (porter stemming, so "streaming" matches "streams"), or semantic KNN when the `[semantic]` extra is installed (see [Semantic retrieval](#semantic-retrieval-optional)). Results are ranked by relevance and truncated to a configurable token budget before prompt injection.

**Storage:** Single `memory.db` file in the project root. Portable, inspectable with `sqlite3`, gitignored by default.

### Semantic retrieval (optional)

By default, `get_context()` retrieves via FTS5/BM25. With the optional `[semantic]` extra installed, FlowState upgrades retrieval to **semantic KNN** over a `sqlite-vec` vector store (`memories_vec`) embedded with [fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`, 384-dim):

- Embeddings are computed on write (`add`/`update`/`add_many`) and existing rows are lazily backfilled on open — never blocking startup.
- Retrieval ranks by vector distance with an L2 relevance floor (≈ cosine 0.60); queries with no relevant match fall back to the same empty result as before.
- **Graceful by design:** if the `[semantic]` extra is absent (or `sqlite-vec`/the model can't load), every path degrades to the existing FTS5/BM25 behavior — byte-identical output, no errors. The core install stays dependency-free.

Why it matters: on a checkable grounding benchmark, naive BM25 surfaced the correct article 3/20 while semantic KNN hit 17/20 (≈ oracle), recovering grounding accuracy lexical retrieval loses. Enable it with `pip install -e ".[semantic]"`.

The embedding model is configurable via `FLOWSTATE_EMBED_MODEL` or `.planning/config.json`.

## Prompt-tuning A/B harness (`bench/`, research-only)

FlowState's prompts are tuned with evidence, not vibes. The `bench/` harness includes an opt-in A/B suite that measures whether a prompt change actually helps *before* anyone adopts it. **None of this runs in the pipeline** — these are manual measurement tools you invoke directly; a deterministic `flowstate` run never calls them.

It builds up in three rungs, each gated on real grounding measurements with Wilson score confidence intervals (binary multi-judge eval over `claude --print`):

- **`--mode promptab`** — A/B two *answer-instruction* variants over a fixed context layer. Decision: `ADOPT_B` only when B beats A **and** their Wilson CIs do not overlap (else `NO_CHANGE`).
- **`--mode sysab`** — A/B two *adapter system prompts* (the strategy adapter). Because the output is a document, not a fact, it uses a **pairwise, position-debiased rubric judge** (both orderings, five strategy dimensions) and a win-rate gate: `ADOPT_B` only when B's win-rate > 0.5 with a Wilson lower bound > 0.5.
- **`bench/tune_loop.py`** — closes the loop: **mine** the probes the live prompt gets wrong → **propose** a candidate via one `claude` call → **gate** it through `promptab` → **emit a human-approval report**. Hard stop: the loop **never edits any source file** and has no `--apply` flag. A human reads the report and makes the one change.

The gate is what keeps self-improvement honest. A candidate mined from a real failure can still *regress* — e.g. a plausible "cite the source / never answer empty" instruction tanks accuracy when there's no context to cite. The bench catches that and returns `NO_CHANGE`. Tuning is measured; adoption is human; the whole loop stays out of the deterministic runtime by design.

```bash
# A/B an answer instruction
python -m bench.grounding --mode promptab --root . --layers none \
  --probes bench/fixtures/grounding_probes.example.json \
  --variant-a bench/fixtures/instr_baseline.txt \
  --variant-b bench/fixtures/instr_candidate.txt --out promptab.json

# closed loop: mine → propose → gate → report (writes tune_report.md, never touches flowstate/)
python -m bench.tune_loop --root . --probes <probes.json> --arm none --out-dir ./.tune_runs
```

## Acknowledgments

FlowState was inspired by and designed to integrate with these projects:

- **[Autoresearch](https://github.com/karpathy/autoresearch)** by Andrej Karpathy — An ML experiment loop (modify, measure, keep/discard). FlowState's research adapter draws on the idea of structured, iterative research but adapts it for general-purpose topic research via Claude.
- **[Gstack](https://github.com/garrytan/gstack)** by Garry Tan — 23 slash commands for Claude Code including `/office-hours` for strategic pressure-testing. FlowState's strategy adapter implements a similar advisor-style evaluation without requiring the Gstack skill installation.
- **[GSD (Get Shit Done)](https://github.com/gsd-build/gsd-2)** — 29 slash commands + 12 specialized agents for project management. FlowState generates the context files GSD consumes (PROJECT.md, ROADMAP.md) and provides `flowstate launch` to hand off to native GSD execution.
- **[Superpowers](https://github.com/obra/claude-code-superpowers)** by Jesse Vincent — A Claude Code plugin enforcing TDD workflow and git worktrees. FlowState's discipline module implements similar project auditing in pure Python.
- **[ECC](https://github.com/affaan-m/ECC)** (`affaan-m`) — An agent-harness performance system. FlowState borrowed several patterns from it: the install-manifest plus `doctor`/`repair` model and env-var hook profiles (v0.3), and the eval-fixture contract format — retrieval questions, acceptance gates, forbidden actions — that `flowstate init` / `flowstate kickoff` scaffold (v0.4). FlowState deliberately did *not* adopt ECC's multi-harness packaging or Rust control-plane.
- **[Andrej Karpathy Skills](https://github.com/multica-ai/andrej-karpathy-skills)** — Behavioral coding guidelines (Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution) distilled from Andrej Karpathy's notes on LLM coding pitfalls. FlowState ships these as the `CANON` constant prepended to every `claude --print` system prompt (v0.4).
- **[Repomix](https://github.com/yamadashy/repomix)** by Kazuki Yamada — Packs a codebase into a single AI-friendly file. `flowstate pack` shells out to the Repomix CLI to produce the codebase pack that FlowState's CAG context layer injects, and registers the Repomix MCP server for retrieval-on-top (v0.4).
- **[sqlite-vec](https://github.com/asg017/sqlite-vec)** by Alex Garcia & **[fastembed](https://github.com/qdrant/fastembed)** by Qdrant — A SQLite vector-search extension and an ONNX-based local embedding library. Together they back FlowState's optional semantic memory retrieval (`[semantic]` extra): `sqlite-vec` stores the `memories_vec` KNN index inside `memory.db`, and `fastembed` (`bge-small-en-v1.5`) produces the embeddings — both fully local, no network at query time (v0.6).

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

FlowState calls external tools via subprocess and does not bundle their code. Users are responsible for complying with the terms of service for any tools they use through FlowState, including [Anthropic's Commercial Terms](https://www.anthropic.com/legal/commercial-terms) for Claude Code.
