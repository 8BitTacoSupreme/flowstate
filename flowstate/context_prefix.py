"""Layered CAG context prefix assembler — Phase 4, CAG-01/02 / Phase 7, GOT-02.

Composes the most-stable-first ordered prefix for all adapter user-prompts:
  fixtures → pack (if it fits) → gotchas → memory → since-last-run

The result is built ONCE per pipeline run in orchestrator.run_pipeline() and
threaded via the existing ``prior_knowledge`` seam into ResearchAdapter,
StrategyAdapter, and GSDAdapter — no adapter calls this function directly.

Layer ordering rationale (most-stable-first for implicit prompt-cache hits):
  1. Fixtures       — static ECC fixture from .planning/fixtures/starter.json.
                      Never changes within a run; stabilises the cache prefix.
  2. Pack           — repomix XML pack at .planning/codebase/repomix-pack.xml.
                      Regenerated only when source files change; semi-stable.
  3. Gotchas        — accumulated failure signals from memory.db (INSIGHT+gotcha).
                      Semi-stable (grows slowly); placed before memory for cache.
  4. Memory         — FTS5 search results from MemoryStore.get_context(query).
                      Most dynamic of the stable layers; placed fourth.
  5. Since Last Run — last N MemoryKind.RUN journal deltas (newest-first).
                      Most dynamic; placed last so it stays outside cache window.

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
import os
from pathlib import Path
from typing import Any

from rich.console import Console

from flowstate.embeddings import get_embedder
from flowstate.memory import MemoryKind
from flowstate.pack import PackResult, run_pack

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_SEPARATOR = "\n\n---\n\n"
_BUDGET_ENV_VAR = "FLOWSTATE_CONTEXT_BUDGET_TOKENS"
_PACK_PATH = ".planning/codebase/repomix-pack.xml"
_WIKI_PATH = ".planning/codebase/wiki.md"
_FIXTURE_PATH = ".planning/fixtures/starter.json"
_CONFIG_PATH = ".planning/config.json"
_DEFAULT_BUDGET_TOKENS = 12_000
_DEFAULT_JOURNAL_PREFIX_N = 3
_DEFAULT_GOTCHAS_MAX_ENTRIES = 10
_DEFAULT_GOTCHAS_BUDGET_TOKENS = 1500
_CHARS_PER_TOKEN = 4  # consistent with memory.py::get_context approximation

_WIKI_CORPUS_DIR = (
    ".planning/codebase/wiki"  # article directory (distinct from single-file _WIKI_PATH)
)
_DEFAULT_WIKI_K = 3  # bench rag-k that yielded 17/20 semantic hits
_WIKI_K_ENV_VAR = "FLOWSTATE_WIKI_K"

# Module-level console — callers can inject their own via the ``console`` param
_console = Console()


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    """Estimate token count using the 4-chars/token approximation from memory.py."""
    return len(text) // _CHARS_PER_TOKEN


def _load_budget(root: Path) -> int:
    """Resolve the context-prefix token budget.

    Precedence: ``FLOWSTATE_CONTEXT_BUDGET_TOKENS`` env var → ``.planning/config.json``
    key ``context_prefix_budget_tokens`` → ``_DEFAULT_BUDGET_TOKENS`` (~12 000).

    The env override exists because the pipeline's Context Generation step rewrites
    config.json every run, so a config-only budget cannot survive a multi-run session
    (e.g. the bench harness). The env var is authoritative and regeneration-proof.
    Only a positive integer is accepted at each tier (booleans excluded); invalid
    values fall through to the next tier. Default behavior is unchanged when unset.
    """
    env_value = os.environ.get(_BUDGET_ENV_VAR)
    if env_value is not None:
        try:
            parsed = int(env_value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_BUDGET_TOKENS
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("context_prefix_budget_tokens")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_BUDGET_TOKENS


def _load_journal_prefix_n(root: Path) -> int:
    """Read run_journal_prefix_entries from .planning/config.json.

    Falls back to ``_DEFAULT_JOURNAL_PREFIX_N`` (3) when the file is absent,
    the key is missing, or the value is not a positive integer (booleans excluded).
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_JOURNAL_PREFIX_N
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("run_journal_prefix_entries")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_JOURNAL_PREFIX_N


def _load_gotchas_max_entries(root: Path) -> int:
    """Read gotchas_max_entries from .planning/config.json.

    Falls back to ``_DEFAULT_GOTCHAS_MAX_ENTRIES`` (10) when the file is absent,
    the key is missing, or the value is not a positive integer (booleans excluded).
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_GOTCHAS_MAX_ENTRIES
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("gotchas_max_entries")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_GOTCHAS_MAX_ENTRIES


def _load_gotchas_budget_tokens(root: Path) -> int:
    """Read gotchas_budget_tokens from .planning/config.json.

    Falls back to ``_DEFAULT_GOTCHAS_BUDGET_TOKENS`` (1500) when the file is absent,
    the key is missing, or the value is not a positive integer (booleans excluded).
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return _DEFAULT_GOTCHAS_BUDGET_TOKENS
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("gotchas_budget_tokens")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    except Exception:
        pass
    return _DEFAULT_GOTCHAS_BUDGET_TOKENS


def _load_gotchas_enabled(root: Path) -> bool:
    """Read gotchas_enabled from .planning/config.json.

    Returns True (default) unless the key is literally the JSON boolean false.
    Non-bool values (strings, ints) fall back to the True default.
    """
    config_path = root / _CONFIG_PATH
    if not config_path.exists():
        return True
    try:
        data: dict[str, Any] = json.loads(config_path.read_text())
        value = data.get("gotchas_enabled")
        if isinstance(value, bool):
            return value
    except Exception:
        pass
    return True


def _load_wiki_k(root: Path) -> int:
    """Resolve the wiki semantic-retrieval top-k value.

    Precedence: ``FLOWSTATE_WIKI_K`` env var → ``.planning/config.json`` key
    ``wiki_retrieval_k`` → ``_DEFAULT_WIKI_K`` (3).

    Only a positive integer (booleans excluded) is accepted at each tier;
    invalid values fall through to the next tier.
    """
    env_value = os.environ.get(_WIKI_K_ENV_VAR)
    if env_value is not None:
        try:
            parsed = int(env_value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass

    config_path = root / _CONFIG_PATH
    if config_path.exists():
        try:
            data: dict[str, Any] = json.loads(config_path.read_text())
            value = data.get("wiki_retrieval_k")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
        except Exception:
            pass

    return _DEFAULT_WIKI_K


def _semantic_wiki_layer(root: Path, query: str, embedder: Any) -> str | None:
    """Retrieve top-k wiki articles by semantic KNN and return a headed string.

    Returns a ``## Codebase Wiki``-headed string of the top-k articles joined by
    ``_SEPARATOR``, or ``None`` to signal the caller to fall back to the static
    ``_read_wiki_layer`` read.

    Returns None when: corpus dir absent/not-a-dir, embedder is None or unavailable,
    sqlite_vec import fails, no non-blank articles, blank query, KNN yields nothing,
    or ANY exception. Never raises.

    No relevance/distance threshold is applied. Unlike memory.get_context there is no
    "must return empty for a garbage query" golden test for the wiki layer — a real run
    query always wants its k most-relevant articles, so the L2/cosine floor from Phase 10
    is intentionally omitted here to keep the seam simple.
    """
    try:
        corpus_dir = root / _WIKI_CORPUS_DIR
        if not corpus_dir.is_dir():
            return None
        if not query or not query.strip():
            return None
        if embedder is None or not embedder.available():
            return None

        contents: list[str] = []
        for p in sorted(corpus_dir.glob("**/*.md")):
            try:
                text = p.read_text(errors="ignore")
                if not text.strip():
                    continue
                contents.append(text)
            except Exception:
                continue

        if not contents:
            return None

        vectors = embedder.embed(contents)
        if not vectors:
            return None
        qvec_list = embedder.embed([query])
        if not qvec_list:
            return None
        qvec = qvec_list[0]

        try:
            import sqlite_vec  # local import — optional dep
        except ImportError:
            return None

        dim = len(qvec)
        conn = __import__("sqlite3").connect(":memory:")
        try:
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            # Re-scope the extension loader OFF immediately after loading (Phase 9 CR-01 /
            # T-11-01 mitigation): the throwaway :memory: conn does not need further
            # extension loads; disabling reduces the tamper surface for the conn's lifetime.
            conn.enable_load_extension(False)
            conn.execute(f"CREATE VIRTUAL TABLE vec_docs USING vec0(embedding float[{dim}])")
            for i, vec in enumerate(vectors):
                conn.execute(
                    "INSERT INTO vec_docs(rowid, embedding) VALUES (?, ?)",
                    (i, sqlite_vec.serialize_float32(vec)),
                )
            rows = conn.execute(
                "SELECT rowid, distance FROM vec_docs"
                " WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (sqlite_vec.serialize_float32(qvec), _load_wiki_k(root)),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return None

        top_k_contents = [contents[r[0]] for r in rows]
        return "## Codebase Wiki\n\n" + _SEPARATOR.join(top_k_contents)
    except Exception:
        return None


def _read_gotchas_layer(root: Path, memory: Any) -> str:
    """Read accumulated gotchas from memory and format as '## Gotchas'.

    Fetches MemoryKind.INSIGHT entries tagged "gotcha", ranks them by
    (count desc, last_seen desc), caps to gotchas_max_entries, then trims
    trailing blocks until the layer fits within gotchas_budget_tokens.

    Returns empty string when disabled, empty, or on any exception.
    Never raises.
    """
    try:
        if not _load_gotchas_enabled(root):
            return ""

        max_entries = _load_gotchas_max_entries(root)
        budget = _load_gotchas_budget_tokens(root)

        # Fetch a wider set to account for tag-filtering; sort after
        raw_entries = memory.get_by_kind(MemoryKind.INSIGHT, limit=max_entries * 5)
        gotchas = [e for e in raw_entries if "gotcha" in e.tags]
        if not gotchas:
            return ""

        # Two-pass stable sort: first by last_seen desc, then by count desc.
        # ISO-8601 strings sort lexicographically so reverse=True is correct.
        gotchas.sort(key=lambda e: e.metadata.get("last_seen", ""), reverse=True)
        gotchas.sort(key=lambda e: -int(e.metadata.get("count", 1)))

        # Cap to max_entries
        gotchas = gotchas[:max_entries]

        # Build the section — one block per gotcha
        blocks: list[str] = []
        for entry in gotchas:
            meta = entry.metadata
            block_lines = [
                f"### {entry.summary}",
                f"- source: {meta.get('source', entry.source)}",
                f"- severity: {meta.get('severity', 'warning')}",
                f"- count: {meta.get('count', 1)}",
                f"- last seen: {meta.get('last_seen', '')}",
                "",
                entry.content.strip(),
            ]
            blocks.append("\n".join(block_lines))

        # Trim trailing blocks until layer fits within token budget
        header = "## Gotchas"
        while blocks:
            layer = header + "\n\n" + "\n\n".join(blocks)
            if _estimate_tokens(layer) <= budget:
                return layer
            blocks.pop()

        # Even the header alone exceeds budget — return empty (no partial heading)
        return ""
    except Exception:
        return ""


def _read_since_last_run_layer(root: Path, memory: Any) -> str:
    """Read last N run-journal entries and format as '## Since Last Run'.

    Returns empty string when the journal is empty (layer omitted silently).
    Never raises.
    """
    try:
        n = _load_journal_prefix_n(root)
        entries = memory.get_by_kind(MemoryKind.RUN, limit=n)
        if not entries:
            return ""
        lines = ["## Since Last Run\n"]
        for entry in entries:
            lines.append(f"### {entry.summary}\n")
            lines.append(entry.content.strip() + "\n\n")
        return "".join(lines).rstrip()
    except Exception:
        return ""


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


def _read_wiki_layer(root: Path) -> str:
    """Read the distilled-CAG architecture wiki and format it under '## Codebase Wiki'.

    Returns empty string when the wiki file is absent or unreadable.
    Never raises.
    """
    wiki_path = root / _WIKI_PATH
    if not wiki_path.exists():
        return ""
    try:
        text = wiki_path.read_text()
    except Exception:
        return ""
    if text:
        return "## Codebase Wiki\n\n" + text
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
    include_layers: frozenset[str] | None = None,
    console: Console | None = None,
) -> str:
    """Assemble the ordered CAG context prefix for the current pipeline run.

    Composes five layers in most-stable-first order:
      fixtures → pack (if it fits) → gotchas → memory → since-last-run

    The fit ladder for the PACK layer:
      1. ``total_tokens < budget`` → inline full pack.
      2. Else → call ``run_pack(root, compress=True)``, re-read pack, retry.
      3. Still over → omit pack entirely and log the decision.

    The since-last-run layer is always included in budget accounting; if
    including it would exceed the budget, the layer is dropped and logged.

    Every omit/compress decision is logged via the Rich console (``console``
    parameter, or a module-level default). Logging is NEVER silent.

    Args:
        root:           Project root directory.
        memory:         MemoryStore instance with a ``get_context(query) -> str``
                        method.
        query:          FTS5 search query forwarded to ``memory.get_context()``.
        budget_tokens:  Maximum token budget for the assembled prefix.  Defaults
                        to the value of ``context_prefix_budget_tokens`` in
                        ``.planning/config.json`` (or ~12 000 if absent).
        include_layers: When ``None`` (default), all five layers are assembled —
                        byte-identical to the no-kwarg call.  Pass a
                        ``frozenset`` of layer key strings to include ONLY those
                        layers; others are excluded at assembly time (their
                        reader helpers are never invoked).  Valid keys are:
                        ``"fixtures"``, ``"pack"``, ``"gotchas"``, ``"memory"``,
                        ``"since_last_run"``.  An empty frozenset returns ``""``.
        console:        Rich Console for compress/omit logging.  Defaults to the
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

    # Assembly-time gate: include_layers=None means all layers (default path,
    # byte-identical to the no-kwarg call).  A frozenset gates each layer by key.
    def _included(key: str) -> bool:
        return include_layers is None or key in include_layers

    # ── Layer 1: fixtures (most stable) ─────────────────────────────────────
    fixtures_layer = _read_fixtures_layer(root) if _included("fixtures") else ""

    # ── Wiki layer (opt-in only — NEVER routed through _included) ────────────
    # include_layers=None means all standard layers (byte-identical default path).
    # Wiki is NOT a standard layer — it is OPT-IN via explicit "wiki" key.
    # Do not use _included("wiki") here: _included returns True for None (default
    # path), which would include wiki on every call and break byte-identity.
    wiki_included = include_layers is not None and "wiki" in include_layers
    if wiki_included:
        # Attempt semantic retrieval first; fall back to the static single-file read when
        # the embedder is absent, sqlite-vec is not installed, the corpus dir does not
        # exist, or any exception occurs.
        _semantic = _semantic_wiki_layer(root, query, get_embedder(root))
        wiki_layer = _semantic if _semantic is not None else _read_wiki_layer(root)
    else:
        wiki_layer = ""

    # ── Layer 3: gotchas (semi-stable failure signals; built early for budget accounting)
    gotchas_layer = _read_gotchas_layer(root, memory) if _included("gotchas") else ""

    # ── Layer 4: memory (most dynamic — built now so we know its size) ───────
    memory_layer = (memory.get_context(query) if query else "") if _included("memory") else ""

    # ── Layer 5: since-last-run (built early so its cost is included in budget checks)
    since_last_run_layer = (
        _read_since_last_run_layer(root, memory) if _included("since_last_run") else ""
    )

    # ── Layer 2: pack (semi-stable, fit-ladder applied) ──────────────────────
    pack_path = root / _PACK_PATH
    pack_exists = pack_path.exists()

    pack_layer = ""
    if pack_exists and _included("pack"):
        pack_raw = _read_pack_layer(root)
        # Gotchas layer is included in the candidate estimate so the fit decision
        # accounts for the gotchas cost (Phase-6 CR-01 lesson).
        candidate = _SEPARATOR.join(
            filter(
                None,
                [
                    fixtures_layer,
                    wiki_layer,
                    pack_raw,
                    gotchas_layer,
                    memory_layer,
                    since_last_run_layer,
                ],
            )
        )
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
                    filter(
                        None,
                        [
                            fixtures_layer,
                            wiki_layer,
                            pack_compressed,
                            gotchas_layer,
                            memory_layer,
                            since_last_run_layer,
                        ],
                    )
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

    # ── Final budget guard — drop most-dynamic layers first ──────────────────
    # Order: since-last-run first (most dynamic), then gotchas. Each drop is
    # logged explicitly — never silent (Phase-6 CR-01 lesson).
    full_assembly = _SEPARATOR.join(
        filter(
            None,
            [
                fixtures_layer,
                wiki_layer,
                pack_layer,
                gotchas_layer,
                memory_layer,
                since_last_run_layer,
            ],
        )
    )
    if since_last_run_layer and _estimate_tokens(full_assembly) >= budget:
        con.print(
            "[red]context_prefix: omit since-last-run layer — full prefix exceeds budget "
            f"({budget} tokens); since-last-run dropped (content lives in memory.db)[/red]"
        )
        since_last_run_layer = ""
        full_assembly = _SEPARATOR.join(
            filter(None, [fixtures_layer, wiki_layer, pack_layer, gotchas_layer, memory_layer])
        )
    if gotchas_layer and _estimate_tokens(full_assembly) >= budget:
        con.print(
            "[red]context_prefix: omit gotchas layer — full prefix still exceeds budget "
            f"({budget} tokens); gotchas dropped (content lives in memory.db)[/red]"
        )
        gotchas_layer = ""

    # ── Assemble final string ─────────────────────────────────────────────────
    layers = [
        fixtures_layer,
        wiki_layer,
        pack_layer,
        gotchas_layer,
        memory_layer,
        since_last_run_layer,
    ]
    non_empty = [layer for layer in layers if layer]
    return _SEPARATOR.join(non_empty)
