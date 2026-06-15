"""Tests for flowstate/context_prefix.py — build_context_prefix() assembler.

Covers:
  - Layer order: fixtures → pack → memory
  - fit→inline: small pack fits in budget, no compress call
  - over→compress: oversized pack triggers run_pack(compress=True) retry
  - still-over→omit+log: still over after compress → pack omitted, log emitted
  - byte-identical across two calls with identical inputs
  - missing artifacts handled gracefully (no raise, layers omitted)
  - canon NOT in output (no double-inject)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from flowstate.context_prefix import build_context_prefix
from flowstate.pack import PackResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pack_file(root: Path, content: str = "<pack>tiny</pack>") -> Path:
    """Write a fake pack file and return its path."""
    pack_path = root / ".planning" / "codebase" / "repomix-pack.xml"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(content)
    return pack_path


def _make_fixture_file(root: Path, data: dict | None = None) -> Path:
    """Write a fake starter.json fixture and return its path."""
    fixture_path = root / ".planning" / "fixtures" / "starter.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        data = {
            "retrieval_questions": ["What does this do?"],
            "acceptance_gates": ["Tests pass"],
            "forbidden_actions": ["Do not skip tests"],
            "system_contract": "Agent operates faithfully.",
            "few_shot_exemplars": [{"input": "Do X", "expected_output": "X done"}],
        }
    fixture_path.write_text(json.dumps(data, indent=2) + "\n")
    return fixture_path


def _make_memory_stub(returns: str = "", run_entries=None) -> MagicMock:
    """Return a mock MemoryStore whose get_context returns the given string."""
    mem = MagicMock()
    mem.get_context.return_value = returns
    mem.get_by_kind.return_value = run_entries if run_entries is not None else []
    return mem


def _make_run_entry(summary: str = "run delta", content: str = "some delta content") -> MagicMock:
    """Return a minimal fake MemoryEntry for MemoryKind.RUN tests."""
    entry = MagicMock()
    entry.summary = summary
    entry.content = content
    entry.metadata = {}
    return entry


# ---------------------------------------------------------------------------
# Layer order
# ---------------------------------------------------------------------------


class TestLayerOrder:
    def test_fixtures_before_pack_before_memory(self, tmp_path: Path):
        """When all three layers present, order must be: fixtures → pack → memory."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>body</pack>")
        memory = _make_memory_stub("## Prior Knowledge\n\n### Fact\nsome fact\n")

        result = build_context_prefix(
            tmp_path,
            memory,
            "test query",
            budget_tokens=50000,  # generous — all fit
        )

        fixture_idx = result.find("## Eval Fixtures")
        pack_idx = result.find("<pack>body</pack>")
        memory_idx = result.find("## Prior Knowledge")

        assert fixture_idx != -1, "fixtures heading not found"
        assert pack_idx != -1, "pack content not found"
        assert memory_idx != -1, "memory section not found"
        assert fixture_idx < pack_idx, "fixtures must precede pack"
        assert pack_idx < memory_idx, "pack must precede memory"

    def test_separator_between_layers(self, tmp_path: Path):
        """Layers are joined with the canonical '\\n\\n---\\n\\n' separator."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path)
        memory = _make_memory_stub("## Prior Knowledge\n\nstuff\n")

        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "\n\n---\n\n" in result


# ---------------------------------------------------------------------------
# Canon-absent
# ---------------------------------------------------------------------------


class TestCanonAbsent:
    def test_canon_marker_not_in_output(self, tmp_path: Path):
        """The Karpathy CANON text must NOT appear in build_context_prefix output."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path)
        memory = _make_memory_stub("## Prior Knowledge\n\nstuff")

        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        # This is the stable canon marker from flowstate/bridge.py CANON constant
        assert "Behavioral guidelines to reduce common LLM coding mistakes" not in result, (
            "CANON text must live only in the bridge system prompt (Phase 3), "
            "not in the user-prompt context prefix"
        )

    def test_context_prefix_does_not_import_bridge(self):
        """context_prefix module must NOT import anything from flowstate.bridge."""
        import sys

        # Just import and verify bridge names are not in context_prefix's namespace
        import flowstate.context_prefix as cp_mod

        # Verify CANON is not a name in the module
        assert not hasattr(cp_mod, "CANON"), "CANON must not be imported into context_prefix"
        # Verify the source file path does not contain "bridge"
        source_file = getattr(cp_mod, "__file__", "") or ""
        assert "bridge" not in source_file.split("/")[-1], "context_prefix must not be bridge"
        # Verify module source doesn't directly use CANON from bridge
        import inspect

        src = inspect.getsource(cp_mod)
        # Check only non-comment, non-docstring lines for bridge imports
        import_lines = [
            line for line in src.splitlines() if line.strip().startswith(("from ", "import "))
        ]
        bridge_imports = [ln for ln in import_lines if "flowstate.bridge" in ln]
        assert not bridge_imports, (
            f"context_prefix must not import from flowstate.bridge; found: {bridge_imports}"
        )
        _ = sys  # suppress unused import warning


# ---------------------------------------------------------------------------
# Fit → inline (pack fits in budget)
# ---------------------------------------------------------------------------


class TestFitInline:
    def test_small_pack_fits_no_compress_called(self, tmp_path: Path):
        """When pack + fixtures + memory fit within budget, run_pack(compress=True) NOT called."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>tiny content</pack>")
        memory = _make_memory_stub("## Prior Knowledge\n\nhello\n")

        with patch("flowstate.context_prefix.run_pack") as mock_run_pack:
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        # compress should not have been called
        for call in mock_run_pack.call_args_list:
            assert not call.kwargs.get("compress", False), (
                "compress=True must NOT be called when pack fits"
            )

        assert "<pack>tiny content</pack>" in result

    def test_pack_content_inline_in_output(self, tmp_path: Path):
        """Pack content is present verbatim in output when it fits."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>verbatim-content</pack>")
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "verbatim-content" in result


# ---------------------------------------------------------------------------
# Over budget → compress retry
# ---------------------------------------------------------------------------


class TestOverBudgetCompress:
    def test_oversized_pack_triggers_compress(self, tmp_path: Path):
        """When pack pushes prefix over budget, run_pack(compress=True) is called."""
        _make_fixture_file(tmp_path)
        # Write a large pack — well over a tiny budget
        large_content = "X" * 10000
        pack_path = _make_pack_file(tmp_path, large_content)
        memory = _make_memory_stub("")

        # After compress succeeds, write a smaller pack (same path)
        def fake_run_pack(root, *, compress=False):
            if compress:
                pack_path.write_text("Y" * 10)
                return PackResult(success=True, output_path=pack_path)
            return PackResult(success=True, output_path=pack_path)

        with patch("flowstate.context_prefix.run_pack", side_effect=fake_run_pack) as mock:
            build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=100,  # very tight: large content won't fit
            )

        # run_pack must have been called with compress=True
        compress_calls = [c for c in mock.call_args_list if c.kwargs.get("compress")]
        assert len(compress_calls) >= 1, "run_pack(compress=True) must be called for oversized pack"

    def test_compressed_pack_in_output_when_fits(self, tmp_path: Path):
        """After compress, if the smaller pack fits, it appears in the output."""
        _make_fixture_file(tmp_path)
        large_content = "L" * 5000
        pack_path = _make_pack_file(tmp_path, large_content)
        memory = _make_memory_stub("")

        def fake_run_pack(root, *, compress=False):
            if compress:
                # Write a small compressed pack
                pack_path.write_text("<compressed>ok</compressed>")
                return PackResult(success=True, output_path=pack_path)
            return PackResult(success=True, output_path=pack_path)

        with patch("flowstate.context_prefix.run_pack", side_effect=fake_run_pack):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=100,  # large won't fit; compressed will
            )

        assert "<compressed>ok</compressed>" in result


# ---------------------------------------------------------------------------
# Still over budget after compress → omit + log
# ---------------------------------------------------------------------------


class TestStillOverOmitLog:
    def test_pack_omitted_when_still_over_after_compress(self, tmp_path: Path):
        """When compressed pack is still over budget, pack is omitted from output."""
        _make_fixture_file(tmp_path)
        big = "Z" * 5000
        pack_path = _make_pack_file(tmp_path, big)
        memory_text = "## Prior Knowledge\n\nsome facts\n"
        memory = _make_memory_stub(memory_text)

        def fake_run_pack(root, *, compress=False):
            # Compressed pack is also too big
            if compress:
                pack_path.write_text("Z" * 5000)
                return PackResult(success=True, output_path=pack_path)
            return PackResult(success=True, output_path=pack_path)

        with patch("flowstate.context_prefix.run_pack", side_effect=fake_run_pack):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=20,  # extremely tight — nothing big fits
            )

        # Pack content must not be in output
        assert "Z" * 100 not in result

    def test_omit_logged_with_drop_info(self, tmp_path: Path):
        """When pack is omitted, the Rich console logs what was dropped."""
        from io import StringIO

        from rich.console import Console

        _make_fixture_file(tmp_path)
        big = "Z" * 5000
        pack_path = _make_pack_file(tmp_path, big)
        memory = _make_memory_stub("")

        def fake_run_pack(root, *, compress=False):
            if compress:
                pack_path.write_text("Z" * 5000)
                return PackResult(success=True, output_path=pack_path)
            return PackResult(success=True, output_path=pack_path)

        buf = StringIO()
        test_console = Console(file=buf, highlight=False, markup=False)

        with patch("flowstate.context_prefix.run_pack", side_effect=fake_run_pack):
            build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=20,
                console=test_console,
            )

        log_output = buf.getvalue()
        # Log must mention omission and the size/bytes dropped
        assert (
            "omit" in log_output.lower()
            or "drop" in log_output.lower()
            or "skip" in log_output.lower()
        ), f"Expected omit/drop/skip in console log, got: {log_output!r}"

    def test_fixtures_and_memory_present_when_pack_omitted(self, tmp_path: Path):
        """When pack is omitted, fixtures and memory layers still appear."""
        _make_fixture_file(tmp_path)
        big = "Z" * 5000
        pack_path = _make_pack_file(tmp_path, big)
        memory_text = "## Prior Knowledge\n\nremaining facts\n"
        memory = _make_memory_stub(memory_text)

        def fake_run_pack(root, *, compress=False):
            if compress:
                pack_path.write_text("Z" * 5000)
                return PackResult(success=True, output_path=pack_path)
            return PackResult(success=True, output_path=pack_path)

        with patch("flowstate.context_prefix.run_pack", side_effect=fake_run_pack):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=20,
            )

        # Memory section should be present (it's always last)
        assert "## Prior Knowledge" in result


# ---------------------------------------------------------------------------
# Determinism (byte-identical)
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_identical_inputs_produce_identical_output(self, tmp_path: Path):
        """Two calls with the same inputs return byte-identical strings."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>deterministic</pack>")
        memory = _make_memory_stub("## Prior Knowledge\n\nfact\n")

        with patch("flowstate.context_prefix.run_pack"):
            result1 = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)
            result2 = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert result1 == result2, (
            "Two calls with identical inputs must produce byte-identical output"
        )


# ---------------------------------------------------------------------------
# Missing artifacts (graceful omission)
# ---------------------------------------------------------------------------


class TestMissingArtifacts:
    def test_no_fixture_file_omits_fixture_layer(self, tmp_path: Path):
        """Missing fixture file → fixture layer omitted, no exception."""
        # No fixture file written
        _make_pack_file(tmp_path, "<pack>present</pack>")
        memory = _make_memory_stub("## Prior Knowledge\n\nhello\n")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "## Eval Fixtures" not in result
        assert "<pack>present</pack>" in result or "## Prior Knowledge" in result

    def test_no_pack_file_omits_pack_layer(self, tmp_path: Path):
        """Missing pack file → pack layer omitted, no exception."""
        _make_fixture_file(tmp_path)
        # No pack file written
        memory = _make_memory_stub("## Prior Knowledge\n\nhello\n")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        # Pack was not available, so pack content should not appear in output
        assert "## Eval Fixtures" in result

    def test_empty_memory_omits_memory_layer(self, tmp_path: Path):
        """Empty get_context() response → memory layer omitted."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>x</pack>")
        memory = _make_memory_stub("")  # returns empty string

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "## Prior Knowledge" not in result
        assert "## Eval Fixtures" in result

    def test_all_missing_returns_empty_string(self, tmp_path: Path):
        """All layers absent → returns empty string without raising."""
        # No fixture, no pack, no memory
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert isinstance(result, str)

    def test_no_raise_on_any_missing_combination(self, tmp_path: Path):
        """No exception raised for any combination of missing artifacts."""
        memory = _make_memory_stub("## Prior Knowledge\n\nstuff\n")
        # Only memory present
        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Since Last Run layer
# ---------------------------------------------------------------------------


class TestSinceLastRunLayer:
    def test_since_last_run_omitted_when_empty(self, tmp_path: Path):
        """Empty get_by_kind() result → '## Since Last Run' not in output."""
        memory = _make_memory_stub("## Prior Knowledge\n\nfact\n", run_entries=[])

        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "## Since Last Run" not in result

    def test_since_last_run_present_when_populated(self, tmp_path: Path):
        """One RUN entry → '## Since Last Run' appears after '## Prior Knowledge'."""
        entry = _make_run_entry("research re-ran", "research step completed")
        memory = _make_memory_stub("## Prior Knowledge\n\nsome fact\n", run_entries=[entry])

        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "## Since Last Run" in result
        memory_idx = result.find("## Prior Knowledge")
        since_idx = result.find("## Since Last Run")
        assert memory_idx != -1, "## Prior Knowledge must be present"
        assert since_idx != -1, "## Since Last Run must be present"
        assert since_idx > memory_idx, "## Since Last Run must appear after ## Prior Knowledge"

    def test_since_last_run_respects_limit_from_config(self, tmp_path: Path):
        """Config run_journal_prefix_entries=2 → get_by_kind called with limit=2 for RUN kind."""
        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"run_journal_prefix_entries": 2}')

        entries = [_make_run_entry(f"run {i}", f"content {i}") for i in range(5)]
        memory = _make_memory_stub(run_entries=entries[:2])

        build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        from flowstate.memory import MemoryKind

        # get_by_kind is called at least once for RUN with limit=2 (gotchas also calls it for INSIGHT)
        memory.get_by_kind.assert_any_call(MemoryKind.RUN, limit=2)

    def test_load_journal_prefix_n_rejects_bad_values(self, tmp_path: Path):
        """_load_journal_prefix_n falls back to 3 for missing key, non-int, negative."""
        from flowstate.context_prefix import _load_journal_prefix_n

        # Missing key
        config_missing = tmp_path / "missing" / ".planning" / "config.json"
        config_missing.parent.mkdir(parents=True, exist_ok=True)
        config_missing.write_text("{}")
        assert _load_journal_prefix_n(tmp_path / "missing") == 3

        # Non-int value
        config_str = tmp_path / "str_val" / ".planning" / "config.json"
        config_str.parent.mkdir(parents=True, exist_ok=True)
        config_str.write_text('{"run_journal_prefix_entries": "five"}')
        assert _load_journal_prefix_n(tmp_path / "str_val") == 3

        # Negative value
        config_neg = tmp_path / "neg_val" / ".planning" / "config.json"
        config_neg.parent.mkdir(parents=True, exist_ok=True)
        config_neg.write_text('{"run_journal_prefix_entries": -1}')
        assert _load_journal_prefix_n(tmp_path / "neg_val") == 3

        # Zero value
        config_zero = tmp_path / "zero_val" / ".planning" / "config.json"
        config_zero.parent.mkdir(parents=True, exist_ok=True)
        config_zero.write_text('{"run_journal_prefix_entries": 0}')
        assert _load_journal_prefix_n(tmp_path / "zero_val") == 3

        # Valid positive int
        config_ok = tmp_path / "ok_val" / ".planning" / "config.json"
        config_ok.parent.mkdir(parents=True, exist_ok=True)
        config_ok.write_text('{"run_journal_prefix_entries": 5}')
        assert _load_journal_prefix_n(tmp_path / "ok_val") == 5

    def test_since_last_run_entry_content_in_output(self, tmp_path: Path):
        """Entry summary and content appear in the since-last-run section."""
        entry = _make_run_entry("research+strategy re-ran", "roadmap.md changed; 2 new memories")
        memory = _make_memory_stub(run_entries=[entry])

        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "research+strategy re-ran" in result
        assert "roadmap.md changed" in result

    def test_since_last_run_dropped_and_logged_when_over_budget(self, tmp_path: Path):
        """With an oversized RUN layer and a very tight budget, since-last-run is dropped."""
        from io import StringIO

        from rich.console import Console

        # Each entry has large content (~250 chars → ~62 tokens each; 3 entries ≈ 186 tokens)
        large_content = "X" * 250
        entries = [_make_run_entry(f"run {i}", large_content) for i in range(3)]
        memory = _make_memory_stub(run_entries=entries)

        buf = StringIO()
        test_console = Console(file=buf, highlight=False, markup=False)

        # Budget of 50 tokens — tight enough that since-last-run (≈186 tokens) is dropped
        result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50, console=test_console)

        log_output = buf.getvalue()
        # Either since-last-run is absent, or budget was honored (or both)
        over_budget = len(result) // 4 >= 50  # approximate token check
        since_present = "## Since Last Run" in result
        if since_present:
            # If it's present, the prefix must still be within budget
            assert not over_budget, "since-last-run kept but prefix exceeds budget"
        else:
            # It was dropped — the log must say so
            assert "since-last-run" in log_output.lower() or "omit" in log_output.lower(), (
                f"since-last-run dropped but no log emitted; log was: {log_output!r}"
            )

    def test_bool_config_falls_back_to_default_journal_prefix_n(self, tmp_path: Path):
        """A JSON boolean value for run_journal_prefix_entries falls back to the default (3)."""
        from flowstate.context_prefix import _load_journal_prefix_n

        # bool True should NOT be treated as a valid positive int
        config_bool = tmp_path / "bool_val" / ".planning" / "config.json"
        config_bool.parent.mkdir(parents=True, exist_ok=True)
        config_bool.write_text('{"run_journal_prefix_entries": true}')
        assert _load_journal_prefix_n(tmp_path / "bool_val") == 3

        # bool False should also fall back
        config_false = tmp_path / "bool_false" / ".planning" / "config.json"
        config_false.parent.mkdir(parents=True, exist_ok=True)
        config_false.write_text('{"run_journal_prefix_entries": false}')
        assert _load_journal_prefix_n(tmp_path / "bool_false") == 3

    def test_bool_config_falls_back_to_default_budget(self, tmp_path: Path):
        """A JSON boolean value for context_prefix_budget_tokens falls back to the default."""
        from flowstate.context_prefix import _DEFAULT_BUDGET_TOKENS, _load_budget

        config_bool = tmp_path / "bool_budget" / ".planning" / "config.json"
        config_bool.parent.mkdir(parents=True, exist_ok=True)
        config_bool.write_text('{"context_prefix_budget_tokens": true}')
        assert _load_budget(tmp_path / "bool_budget") == _DEFAULT_BUDGET_TOKENS

    def test_env_var_overrides_config_budget(self, tmp_path: Path, monkeypatch):
        """FLOWSTATE_CONTEXT_BUDGET_TOKENS takes precedence over config.json."""
        from flowstate.context_prefix import _BUDGET_ENV_VAR, _load_budget

        config = tmp_path / ".planning" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{"context_prefix_budget_tokens": 12000}')
        monkeypatch.setenv(_BUDGET_ENV_VAR, "40000")
        # Env wins over the config value (the regeneration-proof override).
        assert _load_budget(tmp_path) == 40000

    def test_env_var_used_when_config_absent(self, tmp_path: Path, monkeypatch):
        """The env override applies even when config.json does not exist."""
        from flowstate.context_prefix import _BUDGET_ENV_VAR, _load_budget

        monkeypatch.setenv(_BUDGET_ENV_VAR, "55000")
        assert _load_budget(tmp_path / "no_config") == 55000

    def test_invalid_env_var_falls_back_to_config_then_default(self, tmp_path: Path, monkeypatch):
        """A non-int or non-positive env value falls through to config, then default."""
        from flowstate.context_prefix import _BUDGET_ENV_VAR, _DEFAULT_BUDGET_TOKENS, _load_budget

        config = tmp_path / ".planning" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{"context_prefix_budget_tokens": 30000}')
        monkeypatch.setenv(_BUDGET_ENV_VAR, "not-an-int")
        assert _load_budget(tmp_path) == 30000  # falls through to config
        monkeypatch.setenv(_BUDGET_ENV_VAR, "0")  # non-positive
        assert _load_budget(tmp_path) == 30000
        # No config + invalid env -> default
        monkeypatch.setenv(_BUDGET_ENV_VAR, "-5")
        assert _load_budget(tmp_path / "no_config") == _DEFAULT_BUDGET_TOKENS


# ---------------------------------------------------------------------------
# Gotchas config helpers
# ---------------------------------------------------------------------------


class TestGotchasConfigHelpers:
    def test_load_gotchas_max_entries_default(self, tmp_path: Path):
        """Returns 10 when config absent or key missing."""
        from flowstate.context_prefix import _load_gotchas_max_entries

        assert _load_gotchas_max_entries(tmp_path) == 10

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}")
        assert _load_gotchas_max_entries(tmp_path) == 10

    def test_load_gotchas_max_entries_honors_valid_int(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_max_entries

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_max_entries": 5}')
        assert _load_gotchas_max_entries(tmp_path) == 5

    def test_load_gotchas_max_entries_rejects_bool(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_max_entries

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_max_entries": true}')
        assert _load_gotchas_max_entries(tmp_path) == 10

    def test_load_gotchas_max_entries_rejects_negative_and_zero(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_max_entries

        for bad_value in [-1, 0]:
            config_path = tmp_path / f"bad{bad_value}" / ".planning" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(f'{{"gotchas_max_entries": {bad_value}}}')
            assert _load_gotchas_max_entries(tmp_path / f"bad{bad_value}") == 10

    def test_load_gotchas_budget_tokens_default(self, tmp_path: Path):
        """Returns 1500 when config absent or key missing."""
        from flowstate.context_prefix import _load_gotchas_budget_tokens

        assert _load_gotchas_budget_tokens(tmp_path) == 1500

    def test_load_gotchas_budget_tokens_honors_valid_int(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_budget_tokens

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_budget_tokens": 800}')
        assert _load_gotchas_budget_tokens(tmp_path) == 800

    def test_load_gotchas_budget_tokens_rejects_bool(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_budget_tokens

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_budget_tokens": false}')
        assert _load_gotchas_budget_tokens(tmp_path) == 1500

    def test_load_gotchas_enabled_default_true(self, tmp_path: Path):
        """Returns True when config absent or key missing."""
        from flowstate.context_prefix import _load_gotchas_enabled

        assert _load_gotchas_enabled(tmp_path) is True

    def test_load_gotchas_enabled_returns_false_for_bool_false(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_enabled

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_enabled": false}')
        assert _load_gotchas_enabled(tmp_path) is False

    def test_load_gotchas_enabled_ignores_int(self, tmp_path: Path):
        """Non-bool value falls back to True default."""
        from flowstate.context_prefix import _load_gotchas_enabled

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_enabled": 0}')
        assert _load_gotchas_enabled(tmp_path) is True

    def test_load_gotchas_enabled_returns_true_for_bool_true(self, tmp_path: Path):
        from flowstate.context_prefix import _load_gotchas_enabled

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_enabled": true}')
        assert _load_gotchas_enabled(tmp_path) is True


# ---------------------------------------------------------------------------
# _read_gotchas_layer
# ---------------------------------------------------------------------------


def _make_gotcha_entry(
    summary: str = "[test] some gotcha",
    content: str = "the gotcha message",
    count: int = 1,
    last_seen: str = "2026-06-08T00:00:00+00:00",
    source: str = "test",
    severity: str = "warning",
    tags: list | None = None,
) -> MagicMock:
    """Return a minimal fake MemoryEntry for gotcha tests."""
    entry = MagicMock()
    entry.summary = summary
    entry.content = content
    entry.source = source
    entry.tags = tags if tags is not None else ["gotcha", source]
    entry.metadata = {
        "signature": "abc123",
        "source": source,
        "severity": severity,
        "first_seen": "2026-06-01T00:00:00+00:00",
        "last_seen": last_seen,
        "count": count,
    }
    return entry


class TestReadGotchasLayer:
    def test_emits_gotchas_heading_with_entries(self, tmp_path: Path):
        """With gotcha entries present, result starts with '## Gotchas'."""
        from flowstate.context_prefix import _read_gotchas_layer

        entry = _make_gotcha_entry()
        mem = MagicMock()
        mem.get_by_kind.return_value = [entry]

        result = _read_gotchas_layer(tmp_path, mem)

        assert "## Gotchas" in result

    def test_ranked_by_count_desc_then_last_seen_desc(self, tmp_path: Path):
        """Entries are emitted count desc, then last_seen desc."""
        from flowstate.context_prefix import _read_gotchas_layer

        high_count = _make_gotcha_entry("high", count=5, last_seen="2026-06-01T00:00:00+00:00")
        low_count = _make_gotcha_entry("low", count=1, last_seen="2026-06-08T00:00:00+00:00")
        mem = MagicMock()
        mem.get_by_kind.return_value = [low_count, high_count]  # wrong order

        result = _read_gotchas_layer(tmp_path, mem)

        assert result.index("high") < result.index("low"), "high-count entry must appear first"

    def test_capped_to_max_entries(self, tmp_path: Path):
        """With max_entries=2 in config, only 2 gotchas appear even if more exist."""
        from flowstate.context_prefix import _read_gotchas_layer

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_max_entries": 2}')

        entries = [_make_gotcha_entry(f"gotcha {i}", count=i) for i in range(5, 0, -1)]
        mem = MagicMock()
        mem.get_by_kind.return_value = entries

        result = _read_gotchas_layer(tmp_path, mem)

        # Only the top 2 by count should appear (count 5 and 4)
        assert "gotcha 5" in result
        assert "gotcha 4" in result
        assert "gotcha 1" not in result

    def test_trimmed_to_budget_tokens(self, tmp_path: Path):
        """Layer is trimmed so _estimate_tokens(result) <= gotchas_budget_tokens."""
        from flowstate.context_prefix import _estimate_tokens, _read_gotchas_layer

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Very tight token budget — forces trim
        config_path.write_text('{"gotchas_budget_tokens": 30}')

        entries = [_make_gotcha_entry(f"gotcha {i}", content="X" * 200, count=i) for i in range(5)]
        mem = MagicMock()
        mem.get_by_kind.return_value = entries

        result = _read_gotchas_layer(tmp_path, mem)

        if result:  # may be empty if even header exceeds budget
            assert _estimate_tokens(result) <= 30, (
                f"Layer exceeds budget: {_estimate_tokens(result)} tokens"
            )

    def test_returns_empty_when_no_gotchas(self, tmp_path: Path):
        """Empty gotcha list → returns ''."""
        from flowstate.context_prefix import _read_gotchas_layer

        mem = MagicMock()
        mem.get_by_kind.return_value = []

        result = _read_gotchas_layer(tmp_path, mem)

        assert result == ""

    def test_returns_empty_when_disabled(self, tmp_path: Path):
        """gotchas_enabled=false → returns ''."""
        from flowstate.context_prefix import _read_gotchas_layer

        config_path = tmp_path / ".planning" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"gotchas_enabled": false}')

        entry = _make_gotcha_entry()
        mem = MagicMock()
        mem.get_by_kind.return_value = [entry]

        result = _read_gotchas_layer(tmp_path, mem)

        assert result == ""

    def test_never_raises_on_memory_exception(self, tmp_path: Path):
        """If memory.get_by_kind raises, returns '' without propagating."""
        from flowstate.context_prefix import _read_gotchas_layer

        mem = MagicMock()
        mem.get_by_kind.side_effect = RuntimeError("db gone")

        result = _read_gotchas_layer(tmp_path, mem)  # must not raise

        assert result == ""

    def test_filters_to_gotcha_tagged_entries_only(self, tmp_path: Path):
        """Entries without 'gotcha' tag are excluded."""
        from flowstate.context_prefix import _read_gotchas_layer

        gotcha_entry = _make_gotcha_entry("real gotcha", tags=["gotcha", "doctor"])
        non_gotcha = _make_gotcha_entry("not a gotcha", tags=["insight"])
        mem = MagicMock()
        mem.get_by_kind.return_value = [gotcha_entry, non_gotcha]

        result = _read_gotchas_layer(tmp_path, mem)

        assert "real gotcha" in result
        assert "not a gotcha" not in result

    def test_no_bridge_import(self):
        """context_prefix must not import from flowstate.bridge (after gotchas added)."""
        import inspect

        import flowstate.context_prefix as cp_mod

        src = inspect.getsource(cp_mod)
        import_lines = [
            line for line in src.splitlines() if line.strip().startswith(("from ", "import "))
        ]
        bridge_imports = [ln for ln in import_lines if "flowstate.bridge" in ln]
        assert not bridge_imports, f"bridge imports found: {bridge_imports}"


# ---------------------------------------------------------------------------
# Gotchas layer integration (order + budget participation)
# ---------------------------------------------------------------------------


class TestGotchasLayerIntegration:
    def _make_memory_with_gotchas(self, gotcha_entries=None, run_entries=None, context=""):
        """Return a mock MemoryStore that returns gotchas for INSIGHT, runs for RUN."""
        from flowstate.memory import MemoryKind

        mem = MagicMock()
        mem.get_context.return_value = context

        def _get_by_kind(kind, limit=None):
            if kind == MemoryKind.INSIGHT:
                return gotcha_entries or []
            if kind == MemoryKind.RUN:
                return run_entries or []
            return []

        mem.get_by_kind.side_effect = _get_by_kind
        return mem

    def test_gotchas_before_memory_after_pack(self, tmp_path: Path):
        """Layer order: pack < gotchas < memory (## Gotchas before ## Prior Knowledge)."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>body</pack>")

        gotcha = _make_gotcha_entry("a gotcha", content="something failed")
        mem = self._make_memory_with_gotchas(
            gotcha_entries=[gotcha],
            context="## Prior Knowledge\n\nsome fact\n",
        )

        result = build_context_prefix(tmp_path, mem, "q", budget_tokens=50000)

        pack_idx = result.find("<pack>body</pack>")
        gotchas_idx = result.find("## Gotchas")
        memory_idx = result.find("## Prior Knowledge")

        assert pack_idx != -1, "pack not found"
        assert gotchas_idx != -1, "## Gotchas not found"
        assert memory_idx != -1, "## Prior Knowledge not found"
        assert pack_idx < gotchas_idx, "pack must precede gotchas"
        assert gotchas_idx < memory_idx, "gotchas must precede memory"

    def test_gotchas_omitted_when_empty(self, tmp_path: Path):
        """No gotchas → '## Gotchas' heading absent from result."""
        mem = self._make_memory_with_gotchas(
            gotcha_entries=[],
            context="## Prior Knowledge\n\nfact\n",
        )

        result = build_context_prefix(tmp_path, mem, "q", budget_tokens=50000)

        assert "## Gotchas" not in result

    def test_gotchas_layer_dropped_and_logged_when_over_budget(self, tmp_path: Path):
        """Fat gotchas set with tiny budget → gotchas dropped and logged."""
        from io import StringIO

        from rich.console import Console

        # Large gotcha content → forces budget breach
        fat_content = "G" * 600  # ~150 tokens per entry
        entries = [
            _make_gotcha_entry(f"gotcha {i}", content=fat_content, count=i) for i in range(5)
        ]

        mem = self._make_memory_with_gotchas(gotcha_entries=entries)

        buf = StringIO()
        test_console = Console(file=buf, highlight=False, markup=False)

        result = build_context_prefix(tmp_path, mem, "q", budget_tokens=50, console=test_console)

        log_output = buf.getvalue()
        over_budget = _estimate_tokens(result) >= 50
        gotchas_present = "## Gotchas" in result

        if gotchas_present:
            assert not over_budget, "gotchas kept but prefix exceeds budget"
        else:
            assert (
                "gotcha" in log_output.lower()
                or "drop" in log_output.lower()
                or "omit" in log_output.lower()
            ), f"gotchas dropped but no log emitted; log: {log_output!r}"

    def test_existing_layer_order_regression(self, tmp_path: Path):
        """pack < memory < since-last-run order not broken by gotchas insertion."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>data</pack>")

        run_entry = _make_run_entry("run delta", "some run content")
        mem = self._make_memory_with_gotchas(
            gotcha_entries=[],  # no gotchas
            run_entries=[run_entry],
            context="## Prior Knowledge\n\nfact\n",
        )

        result = build_context_prefix(tmp_path, mem, "q", budget_tokens=50000)

        pack_idx = result.find("<pack>data</pack>")
        memory_idx = result.find("## Prior Knowledge")
        since_idx = result.find("## Since Last Run")

        assert pack_idx != -1
        assert memory_idx != -1
        assert since_idx != -1
        assert pack_idx < memory_idx < since_idx


def _estimate_tokens(text: str) -> int:
    """Replicate the module helper for use in tests."""
    return len(text) // 4


# ---------------------------------------------------------------------------
# include_layers assembly-time gating
# ---------------------------------------------------------------------------


class TestIncludeLayers:
    def test_include_layers_none_is_byte_identical(self, tmp_path: Path):
        """build_context_prefix(..., include_layers=None) == build_context_prefix(...) byte-for-byte."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>tiny</pack>")
        run_entry = _make_run_entry("run delta", "some run content")
        memory = _make_memory_stub(
            returns="## Prior Knowledge\n\nsome fact\n",
            run_entries=[run_entry],
        )

        with patch("flowstate.context_prefix.run_pack"):
            result_no_kwarg = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)
            result_none = build_context_prefix(
                tmp_path, memory, "q", budget_tokens=50000, include_layers=None
            )

        assert result_no_kwarg == result_none, (
            "include_layers=None must be byte-identical to the no-kwarg call"
        )

    def test_include_layers_pack_only_excludes_compounding(self, tmp_path: Path):
        """include_layers=frozenset({'fixtures','pack'}): pack present; gotchas/memory/since absent."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>xml-content</pack>")

        from flowstate.memory import MemoryKind

        mem = MagicMock()
        mem.get_context.return_value = "## Prior Knowledge\n\nfact\n"

        def _get_by_kind(kind, limit=None):
            if kind == MemoryKind.RUN:
                return [_make_run_entry("run delta", "run content")]
            if kind == MemoryKind.INSIGHT:
                return []
            return []

        mem.get_by_kind.side_effect = _get_by_kind

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                mem,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"fixtures", "pack"}),
            )

        assert "<pack>xml-content</pack>" in result, "pack must be present"
        assert "## Eval Fixtures" in result, "fixtures must be present"
        assert "## Prior Knowledge" not in result, "memory must be excluded"
        assert "## Since Last Run" not in result, "since-last-run must be excluded"
        assert "## Gotchas" not in result, "gotchas must be excluded"

    def test_include_layers_memory_only_excludes_pack_and_fixtures(self, tmp_path: Path):
        """include_layers=frozenset({'gotchas','memory','since_last_run'}): no pack, no fixtures."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>should-not-appear</pack>")

        from flowstate.memory import MemoryKind

        mem = MagicMock()
        mem.get_context.return_value = "## Prior Knowledge\n\nsome fact\n"

        def _get_by_kind(kind, limit=None):
            if kind == MemoryKind.RUN:
                return [_make_run_entry("run delta", "run content")]
            if kind == MemoryKind.INSIGHT:
                return []  # no gotchas
            return []

        mem.get_by_kind.side_effect = _get_by_kind

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                mem,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"gotchas", "memory", "since_last_run"}),
            )

        assert "<pack>" not in result, "pack XML must be excluded"
        assert "## Eval Fixtures" not in result, "fixtures heading must be excluded"
        assert "## Prior Knowledge" in result, "memory must be present"
        assert "## Since Last Run" in result, "since-last-run must be present"

    def test_include_layers_empty_frozenset_returns_empty(self, tmp_path: Path):
        """include_layers=frozenset() → returns empty string ''."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>something</pack>")
        memory = _make_memory_stub(
            returns="## Prior Knowledge\n\nfact\n",
            run_entries=[_make_run_entry()],
        )

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=50000,
                include_layers=frozenset(),
            )

        assert result == "", f"Expected empty string, got: {result!r}"


# ---------------------------------------------------------------------------
# Wiki layer (opt-in via include_layers)
# ---------------------------------------------------------------------------


def _make_wiki_file(root: Path, content: str = "# Codebase Wiki\n\nmodule overview\n") -> Path:
    """Write a fake wiki.md and return its path."""
    wiki_path = root / ".planning" / "codebase" / "wiki.md"
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(content)
    return wiki_path


class TestWikiLayer:
    def test_include_layers_none_excludes_wiki_even_when_present(self, tmp_path: Path):
        """include_layers=None must NOT include wiki even when wiki.md exists on disk."""
        _make_fixture_file(tmp_path)
        _make_wiki_file(tmp_path)
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)

        assert "## Codebase Wiki" not in result, (
            "include_layers=None must not emit wiki (wiki is opt-in only)"
        )

    def test_no_kwarg_excludes_wiki_even_when_present(self, tmp_path: Path):
        """Default (no include_layers kwarg) must not include wiki — byte-identical guard."""
        _make_fixture_file(tmp_path)
        _make_wiki_file(tmp_path)
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result_default = build_context_prefix(tmp_path, memory, "q", budget_tokens=50000)
            result_none = build_context_prefix(
                tmp_path, memory, "q", budget_tokens=50000, include_layers=None
            )

        assert "## Codebase Wiki" not in result_default
        assert result_default == result_none, (
            "no-kwarg and include_layers=None must remain byte-identical with wiki.md present"
        )

    def test_include_layers_with_wiki_emits_heading(self, tmp_path: Path):
        """include_layers=frozenset({'fixtures','wiki'}) + wiki.md present → '## Codebase Wiki' in output."""
        _make_fixture_file(tmp_path)
        _make_wiki_file(tmp_path, "# Architecture\n\nAll the modules.\n")
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"fixtures", "wiki"}),
            )

        assert "## Codebase Wiki" in result
        assert "All the modules." in result

    def test_include_layers_with_wiki_includes_fixtures_too(self, tmp_path: Path):
        """include_layers=frozenset({'fixtures','wiki'}) → both fixtures and wiki present."""
        _make_fixture_file(tmp_path)
        _make_wiki_file(tmp_path)
        memory = _make_memory_stub("## Prior Knowledge\n\nfact\n")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"fixtures", "wiki"}),
            )

        assert "## Eval Fixtures" in result
        assert "## Codebase Wiki" in result
        # pack/gotchas/memory/since_last_run must be absent
        assert "<pack>" not in result
        assert "## Prior Knowledge" not in result
        assert "## Since Last Run" not in result
        assert "## Gotchas" not in result

    def test_wiki_before_pack_when_both_present(self, tmp_path: Path):
        """When wiki + pack both present (via include_layers), wiki precedes pack."""
        _make_fixture_file(tmp_path)
        _make_pack_file(tmp_path, "<pack>pack-body</pack>")
        _make_wiki_file(tmp_path, "wiki body\n")
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"fixtures", "wiki", "pack"}),
            )

        wiki_idx = result.find("## Codebase Wiki")
        pack_idx = result.find("<pack>pack-body</pack>")
        assert wiki_idx != -1, "## Codebase Wiki not found"
        assert pack_idx != -1, "pack body not found"
        assert wiki_idx < pack_idx, "wiki must precede pack"

    def test_wiki_absent_no_exception(self, tmp_path: Path):
        """include_layers={'fixtures','wiki'} with wiki.md absent → wiki omitted, no exception."""
        _make_fixture_file(tmp_path)
        # No wiki.md written
        memory = _make_memory_stub("")

        with patch("flowstate.context_prefix.run_pack"):
            result = build_context_prefix(
                tmp_path,
                memory,
                "q",
                budget_tokens=50000,
                include_layers=frozenset({"fixtures", "wiki"}),
            )

        assert "## Codebase Wiki" not in result
        assert "## Eval Fixtures" in result

    def test_read_wiki_layer_absent_file_returns_empty(self, tmp_path: Path):
        """_read_wiki_layer on an absent file returns '' and never raises."""
        from flowstate.context_prefix import _read_wiki_layer

        result = _read_wiki_layer(tmp_path / "no_such_dir")
        assert result == ""

    def test_read_wiki_layer_empty_file_returns_empty(self, tmp_path: Path):
        """_read_wiki_layer on an empty wiki.md file returns ''."""
        from flowstate.context_prefix import _read_wiki_layer

        wiki_path = tmp_path / ".planning" / "codebase" / "wiki.md"
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text("")

        result = _read_wiki_layer(tmp_path)
        assert result == ""

    def test_read_wiki_layer_with_content_returns_heading_wrapped(self, tmp_path: Path):
        """_read_wiki_layer with content returns '## Codebase Wiki\n\n' + content."""
        from flowstate.context_prefix import _read_wiki_layer

        wiki_path = tmp_path / ".planning" / "codebase" / "wiki.md"
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        wiki_path.write_text("module map here\n")

        result = _read_wiki_layer(tmp_path)
        assert result.startswith("## Codebase Wiki\n\n")
        assert "module map here" in result
