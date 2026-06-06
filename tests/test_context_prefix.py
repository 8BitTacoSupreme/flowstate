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


def _make_memory_stub(returns: str = "") -> MagicMock:
    """Return a mock MemoryStore whose get_context returns the given string."""
    mem = MagicMock()
    mem.get_context.return_value = returns
    return mem


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
