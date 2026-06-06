"""Layered CAG context prefix assembler — Phase 4, CAG-01/02.

Composes the most-stable-first ordered prefix for all adapter user-prompts:
  fixtures → pack (if it fits) → memory

The result is built ONCE per pipeline run in orchestrator.run_pipeline() and
threaded via the existing ``prior_knowledge`` seam into ResearchAdapter,
StrategyAdapter, and GSDAdapter — no adapter calls this function directly.

Layer ordering rationale (most-stable-first for implicit prompt-cache hits):
  1. Fixtures  — static ECC fixture from .planning/fixtures/starter.json.
                 Never changes within a run; stabilises the cache prefix.
  2. Pack      — repomix XML pack at .planning/codebase/repomix-pack.xml.
                 Regenerated only when source files change; semi-stable.
  3. Memory    — FTS5 search results from MemoryStore.get_context(query).
                 Most dynamic; placed last so earlier layers cache-hit freely.

CRITICAL — canon exclusion:
  The Karpathy coding-guidelines CANON lives in the bridge SYSTEM prompt
  (Phase 3, bridge.py::CANON + inject_canon). Re-emitting it here would
  double-inject it into every user-prompt turn. This module must NOT import
  anything from flowstate.bridge, and must NOT produce CANON text.

Token budget:
  Default is 12 000 tokens (~48 000 chars at 4 chars/token, matching the
  estimate used in memory.py::get_context). Configurable via the
  ``context_prefix_budget_tokens`` key in .planning/config.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from flowstate.pack import PackResult, run_pack

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_SEPARATOR = "\n\n---\n\n"
_PACK_PATH = ".planning/codebase/repomix-pack.xml"
_FIXTURE_PATH = ".planning/fixtures/starter.json"
_CONFIG_PATH = ".planning/config.json"
_DEFAULT_BUDGET_TOKENS = 12_000
_CHARS_PER_TOKEN = 4  # consistent with memory.py::get_context approximation

# Module-level console — callers can inject their own via the ``console`` param
_console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Estimate token count using the 4-chars/token approximation from memory.py."""
    return len(text) // _CHARS_PER_TOKEN


def _load_budget(root: Path) -> int:
    """Read context_prefix_budget_tokens from .planning/config.json.

    Falls back to ``_DEFAULT_BUDGET_TOKENS`` (~12 000) when the file is absent,
    the key is missing, or the value is not a positive integer.
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_BUDGET_TOKENS
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("context_prefix_budget_tokens")
        if isinstance(value, int) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_BUDGET_TOKENS


def _read_fixtures_layer(root: Path) -> str:
    """Read the ECC starter fixture and format it under the '## Eval Fixtures' heading.

    Returns empty string when the file is absent (layer omitted silently).
    """
    fixture_path = root / _FIXTURE_PATH
    if not fixture_path.exists():
        return ""
    try:
        raw = fixture_path.read_text().strip()
        # Validate it's parseable JSON, then re-emit compactly for determinism
        data = json.loads(raw)
        compact = json.dumps(data, indent=2, sort_keys=True)
        return f"## Eval Fixtures\n\n```json\n{compact}\n```"
    except Exception:
        return ""


def _read_pack_layer(root: Path) -> str:
    """Read the repomix pack XML verbatim.

    Returns empty string when the pack file is absent.
    """
    pack_path = root / _PACK_PATH
    if not pack_path.exists():
        return ""
    try:
        return pack_path.read_text()
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def build_context_prefix(
    root: Path,
    memory: Any,
    query: str,
    *,
    budget_tokens: int | None = None,
    console: Console | None = None,
) -> str:
    """Assemble the ordered CAG context prefix for the current pipeline run.

    Composes three layers in most-stable-first order:
      fixtures → pack (if it fits) → memory

    The fit ladder for the PACK layer:
      1. ``total_tokens < budget`` → inline full pack.
      2. Else → call ``run_pack(root, compress=True)``, re-read pack, retry.
      3. Still over → omit pack entirely and log the decision.

    Every omit/compress decision is logged via the Rich console (``console``
    parameter, or a module-level default). Logging is NEVER silent.

    Args:
        root:          Project root directory.
        memory:        MemoryStore instance with a ``get_context(query) -> str``
                       method.
        query:         FTS5 search query forwarded to ``memory.get_context()``.
        budget_tokens: Maximum token budget for the assembled prefix.  Defaults
                       to the value of ``context_prefix_budget_tokens`` in
                       ``.planning/config.json`` (or ~12 000 if absent).
        console:       Rich Console for compress/omit logging.  Defaults to the
                       module-level Console when None.

    Returns:
        A single string with layers joined by ``\\n\\n---\\n\\n``.  Returns ``""``
        when all layers are absent/empty.  Never raises on missing artifacts.

    Token budget default:
        ~12 000 tokens (~48 000 chars).  Configurable via
        ``.planning/config.json`` key ``context_prefix_budget_tokens``.
    """
    con = console or _console
    budget = budget_tokens if budget_tokens is not None else _load_budget(root)

    # ── Layer 1: fixtures (most stable) ─────────────────────────────────────
    fixtures_layer = _read_fixtures_layer(root)

    # ── Layer 3: memory (most dynamic — built now so we know its size) ───────
    memory_layer = memory.get_context(query) if query else ""

    # ── Layer 2: pack (semi-stable, fit-ladder applied) ──────────────────────
    pack_path = root / _PACK_PATH
    pack_exists = pack_path.exists()

    pack_layer = ""
    if pack_exists:
        pack_raw = _read_pack_layer(root)
        candidate = _SEPARATOR.join(filter(None, [fixtures_layer, pack_raw, memory_layer]))
        if _estimate_tokens(candidate) < budget:
            # Rung 1 — fits inline
            pack_layer = pack_raw
        else:
            # Rung 2 — try compress
            pack_bytes_before = len(pack_raw.encode())
            con.print(
                f"[yellow]context_prefix: pack ({pack_bytes_before:,} bytes) exceeds budget "
                f"({budget} tokens); retrying with compress=True[/yellow]"
            )
            compress_result: PackResult = run_pack(root, compress=True)
            if compress_result.success:
                pack_compressed = _read_pack_layer(root)
                candidate2 = _SEPARATOR.join(
                    filter(None, [fixtures_layer, pack_compressed, memory_layer])
                )
                if _estimate_tokens(candidate2) < budget:
                    # Rung 2 success — compressed pack fits
                    pack_layer = pack_compressed
                else:
                    # Rung 3 — still over; omit pack
                    dropped_bytes = len(pack_compressed.encode())
                    con.print(
                        f"[red]context_prefix: omit pack — compressed pack "
                        f"({dropped_bytes:,} bytes) still exceeds budget "
                        f"({budget} tokens); pack layer dropped[/red]"
                    )
                    pack_layer = ""
            else:
                # compress failed — omit pack
                con.print(
                    f"[red]context_prefix: omit pack — compress failed "
                    f"({compress_result.error}); pack layer dropped[/red]"
                )
                pack_layer = ""

    # ── Assemble final string ─────────────────────────────────────────────────
    layers = [fixtures_layer, pack_layer, memory_layer]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
