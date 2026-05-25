"""Tests for status_markdown renderer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import FlowStateModel, ToolStatus
from flowstate.status_markdown import (
    _fmt_artifacts,
    _fmt_duration,
    _fmt_error,
    render_status_markdown,
)


class TestRenderStatusMarkdown:
    def test_includes_header_with_project_name(self, tmp_path: Path):
        state = FlowStateModel()
        state.preferences.project_name = "test-proj"
        out = render_status_markdown(state, tmp_path)
        assert out.startswith("# FlowState Status — test-proj")

    def test_includes_generated_and_version(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        assert "**Generated:**" in out
        assert "**Version:**" in out

    def test_includes_tools_table_header(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        assert "## Tools" in out
        assert "| Tool | Status | Started | Completed | Duration | Artifacts | Error |" in out

    def test_tool_row_for_each_default_tool(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        for tool in ("research", "strategy", "gsd", "discipline"):
            assert f"| {tool} |" in out

    def test_missing_dt_renders_em_dash(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        # Default ToolState has no started_at/completed_at
        assert "—" in out

    def test_active_phase_no_roadmap(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        assert "## Active Phase" in out
        assert "No active phase" in out

    def test_active_phase_unchecked_phase(self, tmp_path: Path):
        state = FlowStateModel()
        (tmp_path / ".planning").mkdir()
        (tmp_path / ".planning" / "ROADMAP.md").write_text(
            "- [x] **Phase 1: Done**\n- [ ] **Phase 2: Operate Safely**\n"
        )
        out = render_status_markdown(state, tmp_path)
        assert "Phase 2: Operate Safely" in out

    def test_memory_section_no_db(self, tmp_path: Path):
        state = FlowStateModel()
        out = render_status_markdown(state, tmp_path)
        assert "## Memory" in out
        assert "memory.db not initialized" in out

    def test_memory_section_with_entries(self, tmp_path: Path):
        state = FlowStateModel()
        with MemoryStore(root=tmp_path) as store:
            store.add(MemoryEntry.create(MemoryKind.RESEARCH, "c", "s"))
            store.add(MemoryEntry.create(MemoryKind.DECISION, "c2", "s2"))
        out = render_status_markdown(state, tmp_path)
        assert "| research | 1 |" in out
        assert "| decision | 1 |" in out
        assert "**Total entries:** 2" in out
        assert "**DB size:**" in out

    def test_never_raises_on_missing_root(self, tmp_path: Path):
        state = FlowStateModel()
        # tmp_path exists but is empty — must not raise
        render_status_markdown(state, tmp_path)


class TestFormatHelpers:
    def test_fmt_duration_completed(self):
        from flowstate.state import ToolState

        ts = ToolState(
            status=ToolStatus.COMPLETED,
            started_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 5, 25, 12, 2, 5, tzinfo=UTC),
        )
        assert _fmt_duration(ts) == "2m 5s"

    def test_fmt_duration_running(self):
        from flowstate.state import ToolState

        ts = ToolState(status=ToolStatus.RUNNING, started_at=datetime.now(UTC))
        assert _fmt_duration(ts) == "running"

    def test_fmt_duration_unstarted(self):
        from flowstate.state import ToolState

        ts = ToolState(status=ToolStatus.READY)
        assert _fmt_duration(ts) == "—"

    def test_fmt_artifacts_truncates(self):
        assert _fmt_artifacts(["a", "b", "c", "d", "e"]) == "a, b, c (+2 more)"

    def test_fmt_artifacts_empty(self):
        assert _fmt_artifacts([]) == "—"

    def test_fmt_error_escapes_pipes(self):
        assert _fmt_error("error | with | pipes") == "error \\| with \\| pipes"


class TestStatusMarkdownCli:
    def _isolate_config(self, tmp_path: Path, monkeypatch):
        import flowstate.config as config_mod

        cfg_dir = tmp_path / ".config_flowstate"
        monkeypatch.setattr(config_mod, "_CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(config_mod, "_CONFIG_FILE", cfg_dir / "config.toml")

    def test_status_no_flags_uses_rich_table(self, tmp_path: Path, monkeypatch):
        """Backward compat: no --markdown means Rich table output (banner present)."""
        from click.testing import CliRunner

        from flowstate.cli import main

        self._isolate_config(tmp_path, monkeypatch)
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--root", str(tmp_path)])
        assert result.exit_code == 0
        # Banner is rendered for non-markdown path
        assert "FlowState" in result.output

    def test_status_markdown_prints_markdown_to_stdout(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner

        from flowstate.cli import main

        self._isolate_config(tmp_path, monkeypatch)
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--markdown", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "# FlowState Status" in result.output
        assert "## Tools" in result.output
        assert "## Memory" in result.output
        # No banner ASCII art in markdown mode
        assert "_____ _" not in result.output

    def test_status_write_default_path(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner

        from flowstate.cli import main

        self._isolate_config(tmp_path, monkeypatch)
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
            result = runner.invoke(
                main,
                ["status", "--markdown", "--write", "--root", str(tmp_path)],
            )
            assert result.exit_code == 0
            default_target = Path(cwd) / "status.md"
            assert default_target.exists()
            assert "# FlowState Status" in default_target.read_text()
            assert "Wrote:" in result.output
            assert str(default_target.resolve()) in result.output

    def test_status_write_explicit_path(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner

        from flowstate.cli import main

        self._isolate_config(tmp_path, monkeypatch)
        runner = CliRunner()
        target = tmp_path / "custom_status.md"
        result = runner.invoke(
            main,
            ["status", "--markdown", "--write", str(target), "--root", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert target.exists()
        assert "# FlowState Status" in target.read_text()

    def test_status_write_implies_markdown(self, tmp_path: Path, monkeypatch):
        """--write without --markdown should still produce markdown."""
        from click.testing import CliRunner

        from flowstate.cli import main

        self._isolate_config(tmp_path, monkeypatch)
        runner = CliRunner()
        target = tmp_path / "implicit.md"
        result = runner.invoke(
            main,
            ["status", "--write", str(target), "--root", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert target.exists()
        assert "# FlowState Status" in target.read_text()

    def test_status_help_lists_new_flags(self):
        from click.testing import CliRunner

        from flowstate.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "--markdown" in result.output
        assert "--write" in result.output
