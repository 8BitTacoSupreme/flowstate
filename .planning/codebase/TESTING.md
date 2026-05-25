# Testing Patterns

**Analysis Date:** 2025-05-25

## Test Framework

**Runner:**
- `pytest` (v9.0+, from `pyproject.toml` dev dependencies)
- Config: `pyproject.toml [tool.pytest.ini_options]`
- Test discovery: `testpaths = ["tests"]`

**Assertion Library:**
- Standard `assert` statements (Python built-in)
- No assertion library imported; plain assertions throughout

**Run Commands:**

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_state.py

# Run specific test class
pytest tests/test_memory.py::TestMemoryStoreCRUD

# Watch mode (requires pytest-watch, not in current stack)
# Manual re-run recommended

# Coverage report
pytest --cov=flowstate --cov-report=html

# Enforce minimum coverage (configured as pre-push hook)
pytest --cov=flowstate --cov-fail-under=80
```

**Configuration (pyproject.toml):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=flowstate --cov-report=term-missing --cov-report=html --cov-fail-under=80"

[tool.coverage.run]
source = ["flowstate"]
omit = ["flowstate/__pycache__/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

## Test File Organization

**Location:**
- Tests co-located in `tests/` directory (separate from source, not within `flowstate/`)
- One test file per module: `tests/test_<module>.py` mirrors `flowstate/<module>.py`
- Example: `tests/test_memory.py` tests `flowstate/memory.py`

**File Structure:**
```
tests/
├── conftest.py              # Shared fixtures
├── test_state.py            # Tests for flowstate/state.py
├── test_memory.py           # Tests for flowstate/memory.py
├── test_cli.py              # Tests for flowstate/cli.py
├── test_config.py           # Tests for flowstate/config.py
├── test_discipline.py       # Tests for flowstate/discipline.py
├── test_context.py          # Tests for flowstate/context.py
├── test_orchestrator.py     # Tests for flowstate/orchestrator.py (core)
├── test_orchestrator_extended.py  # Extended orchestrator tests
├── test_bridge.py           # Tests for flowstate/bridge.py
├── test_events.py           # Tests for flowstate/events/
├── test_memory_handlers.py  # Tests for flowstate/memory_handlers.py
├── test_tools.py            # Tests for flowstate/tools/base.py
├── test_tools_extended.py   # Extended tool adapter tests
├── test_launcher.py         # Tests for flowstate/launcher.py
├── test_interview.py        # Tests for flowstate/interview.py
└── __init__.py              # Empty
```

**Naming:**
- Test functions: `test_<what_is_being_tested>`: `test_default_state()`, `test_save_and_load()`, `test_add_and_get()`
- Test classes: `Test<FeatureOrClass>`: `TestMemoryEntry`, `TestMemoryStoreCRUD`, `TestCheckSetup`
- Test methods in classes: `test_<scenario>`: `test_create_generates_id()`, `test_empty_dir()`, `test_add_and_get()`

## Test Structure

**Suite Organization (example from test_state.py):**

```python
def test_default_state():
    """Standalone test function."""
    state = FlowStateModel()
    assert len(state.tools) == 4
    assert "research" in state.tools


class TestMemoryStoreCRUD:
    """Test class groups related tests."""

    def test_add_and_get(self, store: MemoryStore):
        """Test method using fixture."""
        entry = MemoryEntry.create(MemoryKind.RESEARCH, "content", "summary")
        returned_id = store.add(entry)
        assert returned_id == entry.id
        got = store.get(entry.id)
        assert got is not None
```

**Patterns:**

1. **Setup via fixtures (conftest.py):**
   ```python
   @pytest.fixture()
   def store(tmp_path: Path) -> MemoryStore:
       with MemoryStore(root=tmp_path) as s:
           yield s
   ```

2. **Arrange-Act-Assert:**
   ```python
   def test_save_and_load(tmp_path: Path):
       # Arrange
       state = FlowStateModel()
       state.preferences.project_name = "test-project"

       # Act
       save_state(state, tmp_path)
       loaded = load_state(tmp_path)

       # Assert
       assert loaded.preferences.project_name == "test-project"
   ```

3. **Parametrized tests:** Not observed in codebase. Multiple scenarios use separate functions or class methods.

4. **Assertions are direct:** No assertion helpers; plain `assert condition, optional_message`
   ```python
   assert result.success
   assert state.tools["research"].status == ToolStatus.RUNNING
   assert "research/report.md" in state.tools["research"].artifacts
   assert not result.checks["git_repo"]
   ```

## Mocking

**Framework:** `unittest.mock` (Python standard library) and `monkeypatch` (pytest)

**Patterns (monkeypatch for module/class attributes):**

```python
def test_load_nonexistent_returns_none(tmp_path: Path, monkeypatch):
    """Isolate config file location."""
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", tmp_path / "nope" / "config.toml")
    assert config_mod.load_default_root() is None
```

Example from `test_cli.py`:
```python
@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Route all config reads/writes to a temp directory."""
    cfg_dir = tmp_path / ".config_flowstate"
    cfg_file = cfg_dir / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)
```

**What to Mock:**
- External file system paths: Use `tmp_path` fixture + monkeypatch to redirect config/state files
- Module-level globals: `monkeypatch.setattr(module, "GLOBAL_VAR", test_value)`
- Environment variable dependencies: `monkeypatch.setenv("VAR_NAME", "value")`

**What NOT to Mock:**
- Real dataclass/Pydantic model instantiation — test with real objects
- Deterministic pure functions — call directly and assert output
- Context managers (MemoryStore, EventBus) — use with statement or fixture setup/teardown
- CLI commands via CliRunner — use Click's test runner, not mock subprocess

## Fixtures and Factories

**Test Data (conftest.py):**

```python
@pytest.fixture()
def state() -> FlowStateModel:
    """Default FlowStateModel for testing."""
    return FlowStateModel()

@pytest.fixture()
def memory_store(tmp_path: Path) -> MemoryStore:
    """MemoryStore backed by a temp directory."""
    with MemoryStore(root=tmp_path) as store:
        yield store

@pytest.fixture()
def pipeline_started() -> PipelineStarted:
    return PipelineStarted(source="test-orchestrator")
```

**Populated Stores (test_memory.py):**

```python
@pytest.fixture()
def populated_store(store: MemoryStore) -> MemoryStore:
    """Pre-populated store with sample memories."""
    entries = [
        MemoryEntry.create(
            MemoryKind.RESEARCH,
            "Kafka Streams provides lightweight stream processing...",
            "Kafka Streams overview",
            source="research/report.md",
            tags=["kafka", "streaming"],
            run_id="run-001",
        ),
        # ... more entries
    ]
    store.add_many(entries)
    return store
```

**Location:**
- Shared fixtures: `tests/conftest.py`
- Module-specific fixtures: Top of test file (e.g., `test_memory.py` defines its own `store` fixture at lines 12–15)
- Inline factories: Direct calls like `MemoryEntry.create(...)` in test bodies

## Coverage

**Requirements:**
- Minimum: 80% (enforced in `pyproject.toml fail_under = 80`)
- HTML report generated to `htmlcov/` directory

**View Coverage:**
```bash
# Generate HTML report
pytest --cov=flowstate --cov-report=html

# Open in browser
open htmlcov/index.html
```

**Excluded Lines (from pyproject.toml):**
```toml
exclude_lines = [
    "pragma: no cover",  # Opt-out with # pragma: no cover
    "if __name__ == .__main__.",  # Main block
    "if TYPE_CHECKING:",  # Type-only imports
    "raise NotImplementedError",  # Stub methods
]
```

## Test Types

**Unit Tests:**
- **Scope:** Single function or class method
- **Approach:** Direct call with controlled inputs, assert on outputs
- **Examples:** `test_state.py::test_default_state()`, `test_config.py::test_save_load_roundtrip()`, `test_discipline.py::TestCheckSetup`
- **Isolation:** Use fixtures for setup/teardown; `tmp_path` for file system isolation

**Integration Tests:**
- **Scope:** Multiple modules interacting (e.g., state + config + bridge)
- **Approach:** Full pipeline execution in controlled environment
- **Examples:** `test_orchestrator.py::test_init_dry_run_skip_interview()`, `test_cli.py::test_status_command()` with isolated filesystem
- **Setup:** Usually use `CliRunner(isolated_filesystem=...)` or `tmp_path` + fixtures

**E2E Tests:**
- **Framework:** Not explicitly used
- **Note:** FlowState has no E2E suite; integration tests via Click's CliRunner cover most end-to-end flows

## Common Patterns

**Async Testing:**
- Not applicable — no async code in codebase

**Error Testing (exception verification):**

```python
def test_malformed_toml_returns_none(tmp_path: Path, monkeypatch):
    """Gracefully handle invalid TOML."""
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)
    cfg_file.write_text("not valid [ toml {{{")
    assert config_mod.load_default_root() is None
```

Strategy: Return sentinel (None) on expected exceptions, rather than re-raising.

**State Migrations (version handling):**

```python
def test_migrate_v010_state():
    """Old v0.1.0 state with autoresearch/gstack/superpowers keys gets migrated."""
    old_data = {
        "version": "0.1.0",
        "tools": {
            "autoresearch": {"status": "completed", "artifacts": ["report.md"]},
            "gstack": {"status": "completed", "artifacts": ["strategy.md"]},
            "gsd": {"status": "ready"},
            "superpowers": {"status": "blocked", "error": "timeout"},
        },
    }
    migrated = _migrate_state(old_data)
    assert migrated["version"] == "0.2.0"
    assert "research" in migrated["tools"]
    assert "autoresearch" not in migrated["tools"]
```

**CLI Testing (Click):**

```python
def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "flowstate" in result.output

def test_init_dry_run_skip_interview(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "dry-run" in result.output.lower() or "Pipeline" in result.output
```

## Pre-commit Hook (Testing)

Tests are run as a pre-push hook (not pre-commit):

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: pytest-cov
      name: pytest with coverage (80% min)
      entry: .venv/bin/python -m pytest tests/ --cov=flowstate --cov-fail-under=80 --tb=short -q
      language: system
      types: [python]
      pass_filenames: false
      always_run: true
      stages: [pre-push]
```

Runs on `git push`, fails if coverage drops below 80% or tests fail.

---

*Testing analysis: 2025-05-25*
