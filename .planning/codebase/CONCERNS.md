# Codebase Concerns

**Analysis Date:** 2025-05-25

## Tech Debt

**Monolithic CLI module:**
- Issue: `flowstate/cli.py` is 469 lines with 17 command handlers and substantial inline logic. This violates single-responsibility; CLI should dispatch to submodules, not contain command implementation details.
- Files: `flowstate/cli.py` (lines 42–410)
- Impact: Hard to test individual commands, difficult to extend without touching the monolithic file, and tight coupling between CLI parsing and orchestration logic.
- Fix approach: Extract each command handler group into separate modules (e.g., `flowstate/commands/init.py`, `flowstate/commands/launch.py`, `flowstate/commands/memory.py`, `flowstate/commands/config.py`). Keep main CLI in `cli.py` as dispatcher only.

**Broad exception swallowing in config.py:**
- Issue: Lines 20–23 and 22–23 use bare `except Exception` blocks that silently return `None` on any error (TOML parse failures, file I/O, etc.).
- Files: `flowstate/config.py` (lines 20–23)
- Impact: Real errors (corrupted config, permission issues, missing dirs) are hidden; operators can't debug config state. If config file is malformed, users get silent fallback to cwd with no warning.
- Fix approach: Catch specific exceptions (`tomllib.TOMLDecodeError`, `FileNotFoundError`, `IsADirectoryError`); log or warn via console when fallback occurs. Add validation to `save_default_root()` that ensures the path is valid before writing.

**Deleted planning artifacts in pivot (v2 transition):**
- Issue: Three files deleted without migration path: `.planning/PROJECT.md`, `.planning/config.json`, `CONTEXT.md`. Git status shows deletions; unclear what happens if users have partially completed v0.1.0 setups.
- Files: Deleted files tracked in git diff
- Impact: v0.1.0 users upgrading to v0.2.0 lose artifact references. `flowstate.json` has migration code for tool keys (`_migrate_state()` in `flowstate/state.py:79–103`), but no mention of handling orphaned planning files.
- Fix approach: Document the breaking change in CHANGELOG. In `run_pipeline()`, check for v0.1.0 artifacts and either warn or move them to `.planning/legacy/` before overwriting.

**Subprocess invocation in bridge.py without comprehensive error classification:**
- Issue: `flowstate/bridge.py:155–183` runs `subprocess.run()` with captured output, but only catches `TimeoutExpired` and `FileNotFoundError`. Other runtime errors (encoding issues, shell expansion in env vars) are uncaught.
- Files: `flowstate/bridge.py` (lines 155–183)
- Impact: Unexpected subprocess failures can crash orchestrator mid-pipeline. No retry logic or graceful degradation for transient failures.
- Fix approach: Wrap the `subprocess.run()` call in a broader try/except that handles `OSError`, `UnicodeDecodeError`. Add optional retry with exponential backoff for transient errors (configurable via `BridgeConfig`). Log full stderr + exception type for debugging.

**FTS5 query injection risk (now mitigated, but incomplete):**
- Issue: Lines 194–204 in `flowstate/memory.py` added `_sanitize_fts_query()` to escape FTS5 MATCH syntax, wrapping tokens in double quotes. This prevents FTS5 operators (AND, OR, NEAR, etc.) from being interpreted, but does **not** handle edge cases: empty strings, queries with only operators, or Unicode normalization issues.
- Files: `flowstate/memory.py` (lines 194–204)
- Impact: Queries like `"AND"` or `""` will still parse differently than expected; operator-only queries (`"OR NEAR"`) sanitize to `"\"OR\" \"NEAR\""` which won't match real operators but might confuse users.
- Fix approach: Add regex validation to reject operator-only queries early. Test with fuzzing (e.g., property-based testing with Hypothesis). Consider using `MATCH` with `phrase()` for literal phrase search instead of token wrapping.

**Unclear memory store lifecycle management:**
- Issue: `flowstate/memory.py` creates a connection in `__init__()` and requires explicit `.close()` call. `run_pipeline()` in `orchestrator.py:122` creates `MemoryStore(root=root)` and closes it at line 213, but if an exception occurs before line 213, the connection leaks.
- Files: `flowstate/memory.py` (lines 137–144), `flowstate/orchestrator.py` (lines 122, 213)
- Impact: Long-running pipelines with multiple reruns accumulate open database connections and lock contention on `memory.db`.
- Fix approach: Ensure `MemoryStore` uses context manager pattern throughout. Wrap the memory store creation in a try/finally or use a context manager at the orchestrator level (`with MemoryStore(root=root) as memory:`).

## Known Bugs

**Inconsistent root resolution in launcher.py:**
- Symptoms: `detect_tools()` in `launcher.py:28–50` checks for `.planning` in both `root` and `home`, but `root` is expected to be the project root; checking `$HOME/.planning` is meaningless and will false-positive if user has a `.planning` dir in their home.
- Files: `flowstate/launcher.py` (lines 33–42)
- Trigger: Run `flowstate launch gsd` on a project without `.planning/` but where user has `~/.planning/`.
- Workaround: None; behavior is nonsensical but won't crash.
- Fix: Remove `home` from `detect_tools()`; only check project root. GSD is installed project-by-project, not globally.

**Memory migration not triggered on v0.1.0 → v0.2.0 upgrade:**
- Symptoms: If user has `memory.db` from a v0.1.0 run (unlikely, as memory layer is new), schema might not match new schema in SCHEMA_SQL.
- Files: `flowstate/memory.py` (lines 19–67)
- Trigger: Run `flowstate init` after v0.2.0 upgrade if `memory.db` exists.
- Workaround: Manually delete `memory.db`.
- Fix: Add schema versioning. Check `schema_version` table on open; run migrations if outdated. Document in UPGRADE.md that users should delete `memory.db` if upgrading from v0.1.0.

**Missing `.env` file reading in config stack:**
- Symptoms: FlowState reads `FLOWSTATE_CLAUDE_BIN` env var in `bridge.py:50`, but has no mechanism to load `.env` files. If user sets API keys or configs in `.env`, they're ignored unless explicitly exported.
- Files: `flowstate/bridge.py` (lines 50), `flowstate/config.py` (no `.env` support)
- Trigger: Create `.env` in project root with `FLOWSTATE_CLAUDE_BIN=/path/to/claude`; run `flowstate` without exporting the var.
- Workaround: Export env vars manually before running.
- Fix: Load `.env` via `python-dotenv` in `config.py:load_default_root()` or a new `load_env_config()` function called early in CLI startup.

## Security Considerations

**Unchecked command construction in bridge.py subprocess invocation:**
- Risk: `flowstate/bridge.py:119–149` builds a command list with user-supplied flags (model, budget, effort, allowed_tools) and appends a prompt positional argument. While the `--` separator (line 148) prevents flag injection, the `allowed_tools` parameter is a comma-joined string (line 129) that could include spaces or shell metacharacters if attacker controls preferences.
- Files: `flowstate/bridge.py` (lines 119–149)
- Current mitigation: `BridgeConfig.allowed_tools` comes from internal state (`state.preferences`), not external input. No user-facing API currently allows injection.
- Recommendations: Validate `allowed_tools` entries against a whitelist (e.g., `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`). Add type hints / enums for allowed tool names. Log the final command (redacted for secrets) if `--verbose` flag is added.

**CLAUDE.md generation writes interview answers without sanitization:**
- Risk: `flowstate/context.py:80–110` generates `.claude/CLAUDE.md` containing user-supplied interview answers (core_problem, ten_x_vision, etc.) without HTML/Markdown escaping. If answers contain backticks or YAML-breaking characters, generated file could be malformed.
- Files: `flowstate/context.py` (lines 80–110)
- Current mitigation: Interview answers are freeform text via Rich prompts; no user-supplied code is expected. But if `flowstate` is ever exposed to untrusted input (web UI, API), this is an injection point.
- Recommendations: Use a templating engine (Jinja2) with auto-escaping enabled. Validate interview answers regex (e.g., reject lines starting with `#` without proper quoting). Test with adversarial input (e.g., `core_problem = "---\ninjected: yaml"`, `ten_x_vision = "{{7*7}}"`).

**No secrets filtering in error output:**
- Risk: If `subprocess.run()` in `bridge.py:156` returns stderr containing API keys or auth tokens from `claude` CLI, `result.stderr` (lines 168, 175) is stored in `BridgeResult.error` and may be logged or returned to user without redaction.
- Files: `flowstate/bridge.py` (lines 155–183)
- Current mitigation: `claude` CLI shouldn't leak secrets in stderr under normal circumstances.
- Recommendations: Add a filter function that redacts known secret patterns (API key prefixes, bearer tokens, `BEARER_`, `sk-`, etc.) from stderr before storing in `BridgeResult`. Log full stderr to a debug file only if verbose mode enabled.

## Performance Bottlenecks

**FTS5 search without index hints on large memory stores:**
- Problem: `flowstate/memory.py:206–240` uses `memories_fts MATCH ?` with optional `kind` filter. As memory store grows (100s or 1000s of entries), unindexed substring matches on all columns (summary, content, tags) will slow down.
- Files: `flowstate/memory.py` (lines 206–240)
- Cause: No column-specific weighting or BM25 tuning. FTS5 defaults to rank = -(# of matching terms), not relevance-weighted score.
- Improvement path: Add BM25 parameter tuning (e.g., `tokenize='porter unicode61 remove_diacritics 2'`). Consider column-specific weights (summary matches worth more than content). Add `PRAGMA query_only = 1` to prevent accidental modifications during search. Profile with `EXPLAIN QUERY PLAN` to verify index usage.

**Synchronous CLI file operations with no progress indication:**
- Problem: Commands like `context` (line 213–229 in `cli.py`) call `write_context_files()` which may iterate over large state objects and write multiple files. No progress bar or status indication; user sees frozen terminal for multiple seconds.
- Files: `flowstate/cli.py` (lines 213–229), `flowstate/context.py` (178–line module)
- Cause: Blocking file I/O in Rich console output loop without batching or async.
- Improvement path: Add a Rich progress bar with `Progress()` context. Batch file writes (collect all outputs, then write atomically). For future: consider async I/O with `anyio` if pipeline runs become slower.

**No caching of memory search results across tool runs:**
- Problem: Each tool invocation (research, strategy, gsd) independently queries the memory store via `get_context()` in `orchestrator.py`. No memoization; duplicate queries are re-evaluated.
- Files: `flowstate/orchestrator.py` (implied in tool adapters), `flowstate/memory.py:255–284`
- Cause: Memory is rebuilt on each tool run; no session-level cache.
- Improvement path: Cache search results in `FlowStateModel` or a simple dict-based cache keyed by query. Invalidate cache when new memories are added (in memory handlers).

## Fragile Areas

**Pivot-in-progress work in unstaged files:**
- Files affected: `flowstate/cli.py`, `flowstate/discipline.py`, `flowstate/launcher.py`, `flowstate/memory.py`, `tests/test_cli.py`, `tests/test_discipline.py`, `tests/test_launcher.py`, `flowstate/config.py`, `tests/test_config.py`, `uv.lock`
- Why fragile: Git status shows these files as modified (staged in some cases, uncommitted). The v2 pivot (from subprocess wrapper to context orchestrator) is still in progress. CLI API changes, new config.py module, memory layer enhancements, and test rewrites are all staged but not committed. Any developer action (reset, rebase, cherry-pick) could lose this work.
- Safe modification: Commit the pivot work immediately to preserve it. Add integration tests covering the new CLI commands before further changes. Run full test suite before any rebase.
- Test coverage: New `test_cli.py` (318 lines) covers init, run, status, launch, memory, and config commands, but CLI is 469 lines; ~32% of CLI logic is missing test coverage (edge cases, error handling).

**Orchestrator exception handling in context generation:**
- Files: `flowstate/orchestrator.py:156–162`
- Why fragile: `run_pipeline()` wraps `write_context_files()` in a bare `except Exception` that logs the error and continues. If context generation fails, subsequent tools may fail due to missing files, but orchestrator won't stop the pipeline.
- Safe modification: Split context generation into pre-checks (validate state, check disk space) and write. Fail fast if pre-checks fail. Return a result object with success/error that propagates to pipeline outcome.
- Test coverage: No test for context generation failure scenarios.

**Hard-coded tool order with no validation:**
- Files: `flowstate/orchestrator.py:33` (`TOOL_ORDER = ["research", "strategy", "gsd", "discipline"]`)
- Why fragile: Tool order is hardcoded in `run_pipeline()`. If a new tool is added (or removed), order must be manually updated in two places (TOOL_ORDER, step numbers in comments). No validation that tool exists in state.tools.
- Safe modification: Make TOOL_ORDER data-driven; derive from `state.tools.keys()` and sort by a priority field in `ToolState`. Or add a `@dataclass Phase` with name, priority, executor.
- Test coverage: No test for tool order validation or missing tools.

## Scaling Limits

**SQLite WAL mode not enabled for concurrent memory access:**
- Current capacity: Single-threaded, no concurrent writes. Pipeline runs sequentially.
- Limit: If FlowState becomes multi-threaded or multi-process (e.g., parallel tool invocation), WAL mode must be enabled to avoid SQLite `database is locked` errors.
- Files: `flowstate/memory.py:137–142` (connection setup)
- Scaling path: Add `PRAGMA journal_mode = 'wal';` to connection setup. Test with pytest-xdist parallel test runs (currently tests likely run serially).

**Memory store unbounded growth with no retention policy:**
- Current capacity: No limit on memory entries. Each pipeline run adds entries; `memory.db` grows indefinitely.
- Limit: On disk: `memory.db` could reach 100+ MB after 1000s of runs. On memory: FTS5 virtual table keeps index in RAM.
- Scaling path: Add retention policies (e.g., `--max-memories N`, `--prune-older-than DAYS`). Implement a `memory vacuum` command that compacts and re-indexes.

**No rate limiting on ClaudeBridge invocations:**
- Current capacity: Orchestrator can invoke `claude` CLI up to 5 times per pipeline (research, strategy, GSD, each potentially multiple turns).
- Limit: If `--max-turns` is increased or new tools added, rapid consecutive invocations could exceed API quotas or overwhelm the CLI runtime.
- Scaling path: Add rate limiting via token bucket or sliding window in `ClaudeBridge.run()`. Emit warnings if budget is near limit. Support dry-run mode for testing without consuming quota.

## Dependencies at Risk

**python-dotenv not in pyproject.toml:**
- Risk: Config module may need `.env` file support (see Known Bugs); if added, `python-dotenv` must be declared as a dependency. Currently not listed.
- Impact: Future config enhancement could add an undeclared import.
- Migration plan: Add `python-dotenv >= 1.0.0` to `pyproject.toml` if env file support is added. Alternatively, implement minimal `.env` parser inline (regex-based, no quotes/escapes).

**Rich library version constraints not explicit:**
- Risk: CLI depends on Rich for UI (Panel, Table, Progress). No explicit version constraint in dependencies; could break with Rich 13.x+ API changes.
- Impact: Dependency resolution during pip/uv install could pull incompatible Rich version.
- Migration plan: Audit current Rich usage (Panel, Table, Prompt, Progress). Pin to `rich >= 13.0, < 14.0` (or current major version). Add integration test that verifies CLI rendering (e.g., capture output and validate structure).

## Test Coverage Gaps

**Bridge subprocess execution not fully tested:**
- What's not tested: Error handling for non-standard subprocess failure modes (e.g., broken pipe, output encoding errors, permission denied on claude binary).
- Files: `flowstate/bridge.py` (subprocess.run logic), `tests/test_bridge.py` (only 4436 bytes, likely incomplete)
- Risk: Orchestrator could crash on edge case error that wasn't covered in tests.
- Priority: High — bridge is critical path for all tool invocations.

**Memory store concurrency and WAL mode:**
- What's not tested: Concurrent writes to memory.db (if pipeline ever becomes multi-threaded). FTS5 corruption scenarios.
- Files: `flowstate/memory.py`, `tests/test_memory.py` (8326 bytes, but likely serial-only tests)
- Risk: Silent data corruption or locking issues in production if concurrency is added later.
- Priority: Medium — currently serial, but must be covered before parallelization.

**Config migration path for v0.1.0 → v0.2.0:**
- What's not tested: Loading a v0.1.0 `flowstate.json` with old tool keys, running `flowstate init`, and verifying artifacts are migrated correctly.
- Files: `flowstate/state.py:79–103` (migration code), no test
- Risk: Users upgrading from v0.1.0 lose state or get corrupted migration.
- Priority: Medium — affects all existing users.

**Context file generation with invalid interview answers:**
- What's not tested: Edge cases like empty interview answers, milestones with special characters (newlines, quotes), very long strings.
- Files: `flowstate/context.py` (generation logic), `tests/test_context.py` (5054 bytes; limited coverage)
- Risk: Generated `.claude/CLAUDE.md` or `.planning/ROADMAP.md` could be malformed YAML/Markdown.
- Priority: Medium — affects downstream tool parsing.

**Orchestrator exception recovery paths:**
- What's not tested: Individual tool failures (research fails, strategy succeeds, gsd fails) and their effect on downstream tools and artifact state.
- Files: `flowstate/orchestrator.py` (exception in context gen, tool execution), `tests/test_orchestrator.py` (1859 bytes, minimal)
- Risk: Partial pipeline failure leaves inconsistent state.
- Priority: High — critical for production robustness.

**Memory handlers event dispatch:**
- What's not tested: Events triggered by tool failures or unusual artifacts (e.g., symlinks, missing files, very large files).
- Files: `flowstate/memory_handlers.py`, `tests/test_memory_handlers.py` (4220 bytes)
- Risk: Memory store can miss error context or crash on edge case artifacts.
- Priority: Low — current tests likely cover happy path.

---

*Concerns audit: 2025-05-25*
