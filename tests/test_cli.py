"""Tests for the FlowState CLI."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

import flowstate.config as config_mod
from flowstate.cli import main


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch):
    """Route all config reads/writes to a temp directory so tests never
    touch the real ~/.config/flowstate/config.toml."""
    cfg_dir = tmp_path / ".config_flowstate"
    cfg_file = cfg_dir / "config.toml"
    monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_file)


@pytest.fixture()
def healthy_install(tmp_path, monkeypatch):
    """Create an init'd FlowState project with manifest + memory.db; mock claude CLI as present.

    Uses monkeypatch.setenv (writes to os.environ) so click.testing.CliRunner.invoke()
    picks up FLOWSTATE_CLAUDE_BIN without needing `env=` plumbing per call. This is the
    pattern blessed by plan-checker iteration 1 (W4).
    """
    from flowstate.memory import MemoryStore
    from flowstate.state import FlowStateModel, InstallEntry, save_state

    # Ensure claude CLI check passes — write env BEFORE invoking CLI
    fake_claude = tmp_path / "fake_claude"
    fake_claude.write_text("#!/bin/sh\nexit 0\n")
    fake_claude.chmod(0o755)
    monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))

    # Memory.db
    with MemoryStore(root=tmp_path):
        pass

    # One context file + matching manifest entry
    planning = tmp_path / ".planning"
    planning.mkdir()
    pm = planning / "PROJECT.md"
    pm.write_text("# Project\n")
    checksum = hashlib.sha256(pm.read_bytes()).hexdigest()

    state = FlowStateModel()
    state.install_manifest.append(
        InstallEntry(
            path=".planning/PROJECT.md",
            owner="context",
            kind="context",
            created_at=datetime.now(UTC),
            checksum=checksum,
        )
    )
    state.install_manifest.append(
        InstallEntry(
            path="memory.db",
            owner="memory",
            kind="memory",
            created_at=datetime.now(UTC),
            checksum=None,
        )
    )
    save_state(state, tmp_path)
    return tmp_path


class TestDoctorCommand:
    def test_doctor_healthy_install_exits_zero(self, healthy_install):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_doctor_missing_manifest_file_exits_nonzero(self, tmp_path, monkeypatch):
        from flowstate.memory import MemoryStore
        from flowstate.state import FlowStateModel, InstallEntry, save_state

        fake_claude = tmp_path / "fake_claude"
        fake_claude.write_text("#!/bin/sh\nexit 0\n")
        fake_claude.chmod(0o755)
        monkeypatch.setenv("FLOWSTATE_CLAUDE_BIN", str(fake_claude))

        with MemoryStore(root=tmp_path):
            pass

        state = FlowStateModel()
        state.install_manifest.append(
            InstallEntry(
                path=".planning/MISSING.md",
                owner="context",
                kind="context",
                created_at=datetime.now(UTC),
                checksum="0" * 64,
            )
        )
        save_state(state, tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])
        assert result.exit_code >= 1
        assert "manifest_integrity" in result.output

    def test_doctor_orphan_files_does_not_fail(self, healthy_install):
        # Plant an orphan
        (healthy_install / ".planning" / "EXTRA.md").write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "orphan_files" in result.output
        assert "info" in result.output

    def test_doctor_help_lists_command(self):
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output.lower()


class TestRepairCommand:
    def test_repair_safe_fixes_applied(self, healthy_install):
        # Delete PROJECT.md so the manifest entry is "missing"
        (healthy_install / ".planning" / "PROJECT.md").unlink()
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "regenerated context files" in result.output

    def test_repair_skips_destructive_without_flag(self, healthy_install):
        orphan = healthy_install / ".planning" / "EXTRA.md"
        orphan.write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert orphan.exists()

    def test_repair_apply_destructive_deletes_orphans(self, healthy_install):
        orphan = healthy_install / ".planning" / "EXTRA.md"
        orphan.write_text("orphan")
        runner = CliRunner()
        result = runner.invoke(
            main, ["repair", "--apply-destructive", "--root", str(healthy_install)]
        )
        assert result.exit_code == 0
        assert not orphan.exists()

    def test_repair_help_lists_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--help"])
        assert result.exit_code == 0
        assert "--apply-destructive" in result.output

    def test_repair_no_findings_exits_zero(self, healthy_install):
        runner = CliRunner()
        result = runner.invoke(main, ["repair", "--root", str(healthy_install)])
        assert result.exit_code == 0
        assert "Nothing to repair" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "flowstate" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Context Orchestrator" in result.output


def test_status_command(tmp_path: Path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["status", "--root", str(tmp_path)])
        assert result.exit_code == 0


def test_init_dry_run_skip_interview(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "dry-run" in result.output.lower() or "Pipeline" in result.output


def test_run_dry_run(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--dry-run", "--root", str(tmp_path), "1"],
    )
    assert result.exit_code == 0


def test_check_bridge():
    runner = CliRunner()
    result = runner.invoke(main, ["check"])
    # Will succeed regardless — either finds claude or reports not found
    assert result.exit_code == 0


def test_launch_gsd(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["launch", "--root", str(tmp_path), "gsd", "1"],
    )
    assert result.exit_code == 0
    assert "gsd:plan-phase" in result.output


def test_launch_gsd_no_phase(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["launch", "--root", str(tmp_path), "gsd"],
    )
    assert result.exit_code == 0
    assert "gsd:progress" in result.output


def test_context_command(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["context", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert "context files" in result.output.lower()


def test_init_with_model_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--model", "haiku"],
    )
    assert result.exit_code == 0


def test_init_with_budget_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--budget", "0.25"],
    )
    assert result.exit_code == 0


def test_init_with_effort_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--effort", "low"],
    )
    assert result.exit_code == 0


def test_init_model_persists_in_state(tmp_path: Path):
    """--model flag should persist into flowstate.json preferences."""
    import json

    runner = CliRunner()
    runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path), "--model", "haiku"],
    )
    state_file = tmp_path / "flowstate.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["preferences"]["model"] == "haiku"


def test_run_with_model_flag(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "--dry-run", "--root", str(tmp_path), "--model", "opus", "1"],
    )
    assert result.exit_code == 0


def test_fresh_nothing_to_clean(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "already fresh" in result.output


def _populate_state_with_manifest(tmp_path: Path, paths: list[tuple[str, str]]) -> None:
    """Helper: write a flowstate.json with manifest entries for the given (path, kind) pairs."""
    from datetime import UTC, datetime

    from flowstate.state import FlowStateModel, InstallEntry, save_state

    state = FlowStateModel()
    state.install_manifest = [
        InstallEntry(
            path=p,
            owner="context",
            kind=kind,  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            checksum=None,
        )
        for p, kind in paths
    ]
    save_state(state, tmp_path)


def test_fresh_removes_state_files(tmp_path: Path):
    """fresh --yes --force removes generated artifacts (manifest + orphans) but not source code."""
    # Create the files that init would generate
    (tmp_path / "memory.db").write_text("")
    planning = tmp_path / ".planning"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("")
    (planning / "ROADMAP.md").write_text("")
    (planning / "config.json").write_text("{}")
    research_dir = planning / "research"
    research_dir.mkdir()
    (research_dir / "STACK.md").write_text("")
    top_research = tmp_path / "research"
    top_research.mkdir()
    (top_research / "report.md").write_text("")

    # Populate manifest with files we own; STACK.md will be an orphan
    _populate_state_with_manifest(
        tmp_path,
        [
            (".planning/PROJECT.md", "context"),
            (".planning/ROADMAP.md", "context"),
            (".planning/config.json", "config"),
            ("research/report.md", "research"),
            ("memory.db", "memory"),
        ],
    )

    # Create a source file that should survive
    src = tmp_path / "flowstate"
    src.mkdir()
    (src / "cli.py").write_text("# source")

    runner = CliRunner()
    # --force needed to remove orphans (.planning/research/STACK.md, flowstate.json)
    result = runner.invoke(main, ["fresh", "--yes", "--force", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "Removed" in result.output

    # Generated files should be gone
    assert not (tmp_path / "flowstate.json").exists()
    assert not (tmp_path / "memory.db").exists()
    assert not (planning / "PROJECT.md").exists()
    assert not (planning / "research").exists()
    assert not (tmp_path / "research").exists()

    # Source code untouched
    assert (src / "cli.py").exists()


def test_fresh_preserves_claude_md(tmp_path: Path):
    """fresh does NOT delete .claude/CLAUDE.md unless it's in the manifest."""
    _populate_state_with_manifest(tmp_path, [])
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text("# keep me")

    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--yes", "--root", str(tmp_path)])
    assert result.exit_code == 0
    # .claude/ is not scanned for orphans (only .planning/ and research/)
    assert (claude_dir / "CLAUDE.md").exists()


def test_fresh_cancelled_without_yes(tmp_path: Path):
    """fresh without --yes prompts, and 'n' cancels."""
    _populate_state_with_manifest(tmp_path, [])

    runner = CliRunner()
    result = runner.invoke(main, ["fresh", "--root", str(tmp_path)], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output
    assert (tmp_path / "flowstate.json").exists()


def test_fresh_removes_empty_planning_dir(tmp_path: Path):
    """If .planning/ is empty after cleanup, remove it too."""
    planning = tmp_path / ".planning"
    planning.mkdir()
    (planning / "PROJECT.md").write_text("")

    # Track PROJECT.md in the manifest so fresh owns it
    _populate_state_with_manifest(tmp_path, [(".planning/PROJECT.md", "context")])

    runner = CliRunner()
    # --force so the flowstate.json orphan is also removed
    result = runner.invoke(main, ["fresh", "--yes", "--force", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert not planning.exists()


# ── Config persistence integration tests ─────────────────────────────


def test_init_root_saves_default(tmp_path: Path):
    """init --root /some/path should persist the root to config."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["init", "--dry-run", "--skip-interview", "--root", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert config_mod.load_default_root() == tmp_path.resolve()


def test_init_without_root_does_not_save(tmp_path: Path):
    """init without explicit --root should NOT write config."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init", "--dry-run", "--skip-interview"])
        assert result.exit_code == 0
    assert config_mod.load_default_root() is None


def test_status_picks_up_saved_root(tmp_path: Path):
    """status without --root should use saved default."""
    config_mod.save_default_root(tmp_path)

    runner = CliRunner()
    result = runner.invoke(main, ["status"])
    assert result.exit_code == 0


def test_explicit_root_overrides_saved(tmp_path: Path):
    """Explicit --root should beat saved config."""
    saved = tmp_path / "saved"
    saved.mkdir()
    config_mod.save_default_root(saved)

    explicit = tmp_path / "explicit"
    explicit.mkdir()

    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(explicit)])
    assert result.exit_code == 0


def test_config_show_with_saved_root(tmp_path: Path):
    config_mod.save_default_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    # Rich may line-wrap long paths; strip newlines before checking.
    flat = result.output.replace("\n", "")
    assert str(tmp_path.resolve()) in flat


def test_config_show_empty():
    runner = CliRunner()
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "No default root" in result.output


def test_config_set_root(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(main, ["config", "set-root", str(tmp_path)])
    assert result.exit_code == 0
    assert config_mod.load_default_root() == tmp_path.resolve()


def test_config_clear_root(tmp_path: Path):
    config_mod.save_default_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["config", "clear-root"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()
    assert config_mod.load_default_root() is None


def test_config_clear_root_idempotent():
    runner = CliRunner()
    result = runner.invoke(main, ["config", "clear-root"])
    assert result.exit_code == 0
    assert "No default root" in result.output


# ── kickoff command tests (KICK-01) ──────────────────────────────────


class TestKickoffCommand:
    def test_kickoff_skip_interview_exits_zero(self, tmp_path: Path):
        """kickoff --skip-interview exits 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["kickoff", "--skip-interview", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_kickoff_never_calls_run_pipeline(self, tmp_path: Path, monkeypatch):
        """KICK-01: kickoff must NOT invoke run_pipeline under any circumstances."""
        import flowstate.orchestrator as orch_mod

        pipeline_calls: list = []

        def sentinel(*args, **kwargs):
            pipeline_calls.append(args)

        monkeypatch.setattr(orch_mod, "run_pipeline", sentinel)

        runner = CliRunner()
        result = runner.invoke(main, ["kickoff", "--skip-interview", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert pipeline_calls == [], "kickoff must NOT call run_pipeline"

    def test_kickoff_scaffold_artifacts_exist(self, tmp_path: Path):
        """After kickoff --skip-interview, context files are written."""
        runner = CliRunner()
        result = runner.invoke(main, ["kickoff", "--skip-interview", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".planning" / "PROJECT.md").exists()
        assert (tmp_path / ".planning" / "ROADMAP.md").exists()
        assert (tmp_path / ".planning" / "config.json").exists()
        assert (tmp_path / ".planning" / "fixtures" / "starter.json").exists()
        assert (tmp_path / ".mcp.json").exists()

    def test_kickoff_calls_run_pack_once(self, tmp_path: Path, monkeypatch):
        """kickoff calls run_pack exactly once."""
        import flowstate.pack as pack_mod
        from flowstate.pack import PackResult

        pack_calls: list = []

        def fake_pack(root, *, compress=False):
            pack_calls.append(root)
            return PackResult(
                success=True,
                output_path=root / ".planning" / "codebase" / "repomix-pack.xml",
            )

        monkeypatch.setattr(pack_mod, "run_pack", fake_pack)

        runner = CliRunner()
        result = runner.invoke(main, ["kickoff", "--skip-interview", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert len(pack_calls) == 1

    def test_kickoff_exits_zero_when_pack_fails(self, tmp_path: Path, monkeypatch):
        """kickoff exits 0 (graceful degradation) when run_pack returns success=False."""
        import flowstate.pack as pack_mod
        from flowstate.pack import PackResult

        monkeypatch.setattr(
            pack_mod,
            "run_pack",
            lambda root, **kw: PackResult(
                success=False, exit_code=1, error="repomix CLI not found."
            ),
        )

        runner = CliRunner()
        result = runner.invoke(main, ["kickoff", "--skip-interview", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_kickoff_has_no_pipeline_options(self):
        """kickoff help must NOT include --model, --budget, --effort (pipeline flags)."""
        runner = CliRunner()
        kickoff_help = runner.invoke(main, ["kickoff", "--help"]).output
        init_help = runner.invoke(main, ["init", "--help"]).output
        # pipeline flags present in init
        assert "--model" in init_help
        # pipeline flags absent in kickoff
        assert "--model" not in kickoff_help
        assert "--budget" not in kickoff_help
        assert "--effort" not in kickoff_help


# ── journal command tests (RUN-03) ───────────────────────────────────


class TestJournalCommand:
    def test_journal_empty_exits_zero(self, tmp_path: Path):
        """Fresh store (no RUN entries) → exit 0 and 'no journal entries yet'."""
        runner = CliRunner()
        result = runner.invoke(main, ["journal", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "no journal entries yet" in result.output

    def test_journal_populated_shows_table(self, tmp_path: Path):
        """Two RUN entries in store → exit 0 and both run_ids appear in output."""
        from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

        store = MemoryStore(root=tmp_path)
        store.add(
            MemoryEntry.create(
                MemoryKind.RUN,
                content="run detail alpha",
                summary="first run delta",
                run_id="alpha001",
                metadata={"delta_line": "research re-ran", "dry_run": False},
            )
        )
        store.add(
            MemoryEntry.create(
                MemoryKind.RUN,
                content="run detail beta",
                summary="second run delta",
                run_id="beta002",
                metadata={"delta_line": "strategy changed", "dry_run": True},
            )
        )
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["journal", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "alpha001" in result.output
        assert "beta002" in result.output

    def test_journal_limit_option(self, tmp_path: Path):
        """--limit 2 with 5 seeded entries shows only 2 run_ids in output."""
        from datetime import UTC, datetime, timedelta

        from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

        # Use distinct timestamps so ORDER BY created_at DESC is deterministic
        base_ts = datetime(2026, 1, 1, tzinfo=UTC)
        run_ids = [f"rid{i:03d}" for i in range(5)]
        store = MemoryStore(root=tmp_path)
        for i, rid in enumerate(run_ids):
            entry = MemoryEntry.create(
                MemoryKind.RUN,
                content=f"detail {rid}",
                summary=f"delta {rid}",
                run_id=rid,
                metadata={"delta_line": f"delta {rid}", "dry_run": False},
            )
            entry.created_at = base_ts + timedelta(seconds=i)
            store.add(entry)
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["journal", "--limit", "2", "--root", str(tmp_path)])
        assert result.exit_code == 0

        # Newest-first: last 2 inserted are rid003 and rid004
        present = [rid for rid in run_ids if rid in result.output]
        assert len(present) == 2
        # The 3 oldest (rid000, rid001, rid002) must be absent
        for old_id in run_ids[:3]:
            assert old_id not in result.output

    def test_journal_corrupt_db_exits_zero(self, tmp_path: Path):
        """Corrupt memory.db → exit 0 and 'no journal entries yet' (no traceback)."""
        db_path = tmp_path / "memory.db"
        db_path.write_text("this is not a valid sqlite database")

        runner = CliRunner()
        result = runner.invoke(main, ["journal", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "no journal entries yet" in result.output
        assert "Traceback" not in result.output


# ── gotchas command tests (GOT-03) ───────────────────────────────────


def _seed_gotcha(
    store,
    *,
    signature: str,
    source: str = "doctor",
    severity: str = "error",
    count: int = 1,
    last_seen: str = "2026-01-01T00:00:00",
    message: str = "test gotcha",
    tags: list | None = None,
):
    """Seed a gotcha INSIGHT entry directly for test isolation."""
    from datetime import UTC, datetime

    from flowstate.memory import MemoryEntry, MemoryKind

    entry = MemoryEntry.create(
        MemoryKind.INSIGHT,
        content=message,
        summary=f"[{source}] {message[:80]}",
        source=source,
        tags=(tags if tags is not None else ["gotcha", source]),
        metadata={
            "signature": signature,
            "source": source,
            "severity": severity,
            "first_seen": "2026-01-01T00:00:00",
            "last_seen": last_seen,
            "count": count,
        },
    )
    # fix created_at so ordering is deterministic
    entry.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    store.add(entry)
    return entry


class TestGotchasCommand:
    def test_gotchas_empty_exits_zero(self, tmp_path: Path):
        """Fresh root (no memory.db) → exit 0 and 'no gotchas recorded yet'."""
        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "no gotchas recorded yet" in result.output

    def test_gotchas_corrupt_db_exits_zero(self, tmp_path: Path):
        """Corrupt memory.db → exit 0, no Traceback in output."""
        db_path = tmp_path / "memory.db"
        db_path.write_text("not a valid sqlite database")
        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Traceback" not in result.output

    def test_gotchas_populated_shows_table(self, tmp_path: Path):
        """Two gotchas in store → exit 0, both message texts visible in output."""
        from flowstate.memory import MemoryStore

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(
            store,
            signature="aaaa0000bbbb0001",
            source="doctor",
            count=3,
            message="hook missing alpha",
        )
        _seed_gotcha(
            store,
            signature="cccc1111dddd0002",
            source="repair",
            count=1,
            message="state corrupt beta",
        )
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        # Check message content (wide column, not truncated by terminal width)
        assert "hook missing alpha" in result.output
        assert "state corrupt beta" in result.output

    def test_gotchas_sorted_count_desc(self, tmp_path: Path):
        """Higher-count gotcha appears before lower-count gotcha in output."""
        from flowstate.memory import MemoryStore

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(store, signature="low0000000000001", count=1, message="msg LOW COUNT ENTRY")
        _seed_gotcha(store, signature="high000000000002", count=5, message="msg HIGH COUNT ENTRY")
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "--root", str(tmp_path)], env={"COLUMNS": "200"})
        assert result.exit_code == 0
        low_idx = result.output.find("msg LOW COUNT ENTRY")
        high_idx = result.output.find("msg HIGH COUNT ENTRY")
        assert high_idx != -1 and low_idx != -1
        assert high_idx < low_idx, "higher-count gotcha should appear first"

    def test_gotchas_limit_option(self, tmp_path: Path):
        """--limit 1 shows exactly one row when two gotchas are seeded."""
        from flowstate.memory import MemoryStore

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(store, signature="sig1000000000001", count=2, message="FIRSTGOTCHAMSG unique")
        _seed_gotcha(store, signature="sig2000000000002", count=1, message="SECONDGOTCHAMSG unique")
        store.close()

        runner = CliRunner()
        result = runner.invoke(
            main, ["gotchas", "--limit", "1", "--root", str(tmp_path)], env={"COLUMNS": "200"}
        )
        assert result.exit_code == 0
        # Only the higher-count one (sig1) should appear
        assert "FIRSTGOTCHAMSG" in result.output
        assert "SECONDGOTCHAMSG" not in result.output


class TestGotchasPruneCommand:
    def test_prune_by_signature_removes_entry(self, tmp_path: Path):
        """prune --signature <sig> removes that entry; subsequent list no longer shows it."""
        from flowstate.memory import MemoryStore

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(store, signature="deadbeefdeadbeef", message="PRUNETARGET unique msg")
        _seed_gotcha(store, signature="keepmeepkeepmee1", message="KEEPTHISONE unique msg")
        store.close()

        runner = CliRunner()
        result = runner.invoke(
            main, ["gotchas", "prune", "--signature", "deadbeefdeadbeef", "--root", str(tmp_path)]
        )
        assert result.exit_code == 0

        # List should no longer contain the pruned message; kept entry still present
        list_result = runner.invoke(
            main, ["gotchas", "--root", str(tmp_path)], env={"COLUMNS": "200"}
        )
        assert "PRUNETARGET" not in list_result.output
        assert "KEEPTHISONE" in list_result.output

    def test_prune_resolved_removes_resolved_entries(self, tmp_path: Path):
        """prune --resolved clears entries tagged 'resolved', leaves others intact."""
        from flowstate.memory import MemoryStore

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(
            store,
            signature="resolvedaaaaaa01",
            message="RESOLVEDMSG unique gotcha",
            tags=["gotcha", "doctor", "resolved"],
        )
        _seed_gotcha(
            store,
            signature="activebbbbbbbb02",
            message="ACTIVEMSG unique gotcha",
            tags=["gotcha", "doctor"],
        )
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["gotchas", "prune", "--resolved", "--root", str(tmp_path)])
        assert result.exit_code == 0

        list_result = runner.invoke(
            main, ["gotchas", "--root", str(tmp_path)], env={"COLUMNS": "200"}
        )
        assert "RESOLVEDMSG" not in list_result.output
        assert "ACTIVEMSG" in list_result.output

    def test_prune_rewrites_gotchas_md(self, tmp_path: Path):
        """After prune, GOTCHAS.md does not contain the pruned signature."""
        from flowstate.memory import MemoryStore

        # Ensure .planning dir exists for GOTCHAS.md
        (tmp_path / ".planning").mkdir(parents=True, exist_ok=True)

        store = MemoryStore(root=tmp_path)
        _seed_gotcha(store, signature="pruneme00000001a", message="prune target")
        store.close()

        runner = CliRunner()
        runner.invoke(
            main, ["gotchas", "prune", "--signature", "pruneme00000001a", "--root", str(tmp_path)]
        )

        gotchas_md = tmp_path / ".planning" / "GOTCHAS.md"
        if gotchas_md.exists():
            assert "pruneme00000001a" not in gotchas_md.read_text()


# ── doctor/repair gotcha capture tests (GOT-01) ──────────────────────


class TestDoctorGotchaCapture:
    def test_doctor_captures_error_findings(self, tmp_path: Path, monkeypatch):
        """doctor captures error-severity diagnoses as gotchas in memory.db."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.memory import MemoryKind, MemoryStore
        from flowstate.state import FlowStateModel

        fake_findings = [
            Diagnosis(
                name="manifest_integrity", severity="error", message="Manifest file missing: foo"
            ),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
        ):
            result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])

        # doctor exit code = number of errors (1 here)
        assert result.exit_code == 1

        # Gotcha should be in memory.db
        store = MemoryStore(root=tmp_path)
        entries = store.get_by_kind(MemoryKind.INSIGHT, limit=50)
        store.close()
        gotchas = [e for e in entries if "gotcha" in e.tags]
        assert len(gotchas) >= 1
        assert any(e.metadata.get("source") == "doctor" for e in gotchas)
        assert any("Manifest file missing" in e.content for e in gotchas)

    def test_doctor_skips_info_findings(self, tmp_path: Path):
        """doctor does NOT capture info-severity diagnoses as gotchas."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.memory import MemoryKind, MemoryStore
        from flowstate.state import FlowStateModel

        fake_findings = [
            Diagnosis(name="info_check", severity="info", message="This is informational only"),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
        ):
            result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])

        # No errors → exit 0
        assert result.exit_code == 0

        store = MemoryStore(root=tmp_path)
        entries = store.get_by_kind(MemoryKind.INSIGHT, limit=50)
        store.close()
        gotchas = [e for e in entries if "gotcha" in e.tags]
        assert len(gotchas) == 0

    def test_doctor_exit_code_unchanged_by_capture(self, tmp_path: Path):
        """doctor exit code is still error_count even when capture runs."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.state import FlowStateModel

        fake_findings = [
            Diagnosis(name="c1", severity="error", message="err one"),
            Diagnosis(name="c2", severity="error", message="err two"),
            Diagnosis(name="c3", severity="warning", message="warn one"),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
        ):
            result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])

        assert result.exit_code == 2  # two errors

    def test_doctor_capture_failure_does_not_change_exit(self, tmp_path: Path):
        """Corrupt memory.db does not change doctor exit code."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.state import FlowStateModel

        db_path = tmp_path / "memory.db"
        db_path.write_text("corrupt")

        fake_findings = [
            Diagnosis(name="c1", severity="error", message="something broke"),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
        ):
            result = runner.invoke(main, ["doctor", "--root", str(tmp_path)])

        assert result.exit_code == 1  # still 1 error


class TestRepairGotchaCapture:
    def test_repair_captures_error_and_warning_findings(self, tmp_path: Path):
        """repair captures error/warning diagnoses as gotchas."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.memory import MemoryKind, MemoryStore
        from flowstate.state import FlowStateModel

        fake_findings = [
            Diagnosis(name="c1", severity="error", message="state.json missing"),
            Diagnosis(name="c2", severity="warning", message="stale lock file"),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
            patch("flowstate.repair.apply_safe_fixes", return_value=[]),
            patch("flowstate.state.save_state"),
        ):
            result = runner.invoke(main, ["repair", "--root", str(tmp_path)])

        # repair exits 0 (no sys.exit on repair)
        assert result.exit_code == 0

        store = MemoryStore(root=tmp_path)
        entries = store.get_by_kind(MemoryKind.INSIGHT, limit=50)
        store.close()
        gotchas = [e for e in entries if "gotcha" in e.tags]
        assert len(gotchas) >= 2
        sources = {e.metadata.get("source") for e in gotchas}
        assert "doctor" in sources

    def test_repair_exit_code_unchanged_by_capture(self, tmp_path: Path):
        """repair always exits 0 regardless of capture."""
        from unittest.mock import patch

        from flowstate.doctor import Diagnosis
        from flowstate.state import FlowStateModel

        fake_findings = [
            Diagnosis(name="c1", severity="error", message="something failed"),
        ]

        runner = CliRunner()
        with (
            patch("flowstate.state.load_state", return_value=FlowStateModel()),
            patch("flowstate.doctor.run_doctor", return_value=fake_findings),
            patch("flowstate.repair.apply_safe_fixes", return_value=[]),
            patch("flowstate.state.save_state"),
        ):
            result = runner.invoke(main, ["repair", "--root", str(tmp_path)])

        assert result.exit_code == 0
