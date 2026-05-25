# Technology Stack

**Analysis Date:** 2026-05-25

## Languages

**Primary:**
- Python 3.12+ - All source code in `flowstate/`, tests in `tests/`

**Secondary:**
- YAML - Configuration (`pyproject.toml`, `.pre-commit-config.yaml`)
- SQL - Schema and queries in `flowstate/memory.py` (SQLite with FTS5 virtual tables)

## Runtime

**Environment:**
- Python 3.12+ (specified in `pyproject.toml` and `uv.lock`)
- SQLite 3 - Bundled with Python, used for persistent memory store

**Package Manager:**
- `uv` - Modern Python package manager (lockfile: `uv.lock`)
- Entry point: `flowstate = "flowstate.cli:main"` (defined in `pyproject.toml`)

## Frameworks

**Core:**
- `click>=8.1` - CLI framework for command/group structure (`flowstate/cli.py`)
- `pydantic>=2.0` - Data validation and configuration models (`flowstate/state.py`)
- `rich>=13.0` - Terminal UI rendering (tables, panels, formatting in `flowstate/cli.py`)

**Testing:**
- `pytest>=9.0` - Test runner
- `pytest-cov>=7.0` - Coverage reporting (80% minimum enforced)

**Build/Dev:**
- `ruff>=0.15` - Linter and formatter (configured in `pyproject.toml`)
- `pre-commit>=4.0` - Git hooks for linting, formatting, and coverage checks (`.pre-commit-config.yaml`)
- `hatchling` - Build backend (specified in `pyproject.toml`)

## Key Dependencies

**Critical:**
- `sqlite-vec>=0.1.6` - Vector storage extension for SQLite FTS5 (used in `flowstate/memory.py` for semantic search)
- `click` - Powers all CLI commands and options
- `pydantic` - Powers type-safe state models and validation
- `rich` - Provides styled console output (tables, panels, colors)

**Infrastructure:**
- `pre-commit` - Enforces code quality before commits (linting, formatting, coverage gates)
- `coverage` - Measures test coverage; fail if below 80%

## Configuration

**Environment:**
- `.env` file (local, not committed) - Stores EXA_API_KEY for semantic search
- `.env.example` - Template showing required variables
- `~/.config/flowstate/config.toml` - Persistent user config (default project root)

**Build:**
- `pyproject.toml` - Single source of truth for dependencies, version, entry points, tool configs
- `uv.lock` - Locked dependency tree (production-ready pinning)
- `.pre-commit-config.yaml` - Git hook definitions (Ruff, pytest-cov, trailing-whitespace)

## Platform Requirements

**Development:**
- macOS/Linux/Windows with Python 3.12+
- `uv` package manager for dependency isolation
- Flox environment (optional, for reproducibility)
- Git (required for pre-commit hooks)

**Production:**
- Python 3.12+ runtime
- SQLite 3 (bundled with Python)
- `claude` CLI binary available in PATH or via `FLOWSTATE_CLAUDE_BIN` env var
- Terminal with 80+ character width (for Rich formatting)

## Tooling

**Code Quality:**
- Ruff (linting + formatting): python style check and auto-fix
  - Target Python 3.12
  - Line length: 100 characters
  - Rules: E, W, F, I (isort), N (PEP8 naming), UP, B, SIM, RUF
  - Excluded: E501 (line too long; handled by formatter)

**Testing:**
- pytest runs on every `git push` (pre-commit hook)
- Minimum coverage: 80% (coverage report: `htmlcov/index.html`)
- Command: `python -m pytest tests/ --cov=flowstate --cov-fail-under=80`

**Git Workflow:**
- Pre-commit hooks enforce: Ruff check/format → pytest with coverage → standard checks (trailing whitespace, EOF fixer, YAML validation, merge conflict detection)
- Non-blocking before commit; blocking before push (pytest-cov)

---

*Stack analysis: 2026-05-25*
