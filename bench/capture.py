"""Pure snapshot reads for the compounding harness — never raises.

``capture_run_snapshot`` reads a project root through the *real* FlowState
substrate (memory, verify, prefix) and distills it into a ``RunSnapshot`` the
metrics core consumes. Every read is wrapped so any failure degrades to zeros /
empty layers rather than raising — matching the never-raises discipline of
verify.py / gotchas.py / journal.

The single ``_LAYER_HEADINGS`` constant is the only place the layer heading
strings live; a test in tests/test_bench_compound.py asserts it matches the
headings emitted by flowstate/context_prefix.py and fails loudly on drift.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

from bench.metrics import RunSnapshot
from flowstate.context_prefix import build_context_prefix
from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore
from flowstate.state import load_state
from flowstate.verify import run_verify

# The four markdown headings the assembled prefix carries, in layer order. The
# fifth layer (pack) is headerless repomix XML and is detected via tag presence,
# not a heading. This is the SINGLE source of truth for the headings; a test
# couples it to the emitting modules (context_prefix.py emits three, memory.py's
# get_context emits "## Prior Knowledge") and fails loudly if a heading changes.
_LAYER_HEADINGS: tuple[str, ...] = (
    "## Eval Fixtures",
    "## Gotchas",
    "## Prior Knowledge",
    "## Since Last Run",
)

# Tags / markers that indicate the (headerless) pack layer is present.
_PACK_MARKERS: tuple[str, ...] = ("<repomix", "<file ")

# 4 chars/token, matching memory.py / context_prefix.py.
_CHARS_PER_TOKEN = 4


def _zeroed_snapshot(run_index: int, run_id: str) -> RunSnapshot:
    """A fully-zeroed snapshot used when reads fail or the project is empty."""
    return RunSnapshot(
        run_index=run_index,
        run_id=run_id,
        artifacts_changed=0,
        new_gotchas=0,
        reencountered_gotchas=0,
        verify_pass=0,
        verify_fail=0,
        verify_skip=0,
        prefix_tokens=0,
        mem_hits=0,
        layers_present=(),
        tokens_in=0,
        tokens_out=0,
        cache_read=0,
        wall_clock_s=None,
    )


def _is_new_gotcha(entry: MemoryEntry, run_id: str, window_start: datetime | None) -> bool:
    """Attribute a gotcha as new this run: run_id first, created_at window fallback.

    Two attribution rules, applied in order:
    - run_id-first: if the entry's run_id equals the current run_id, it is new.
      This is the exact, unambiguous rule, but it only fires when the CALLER
      controls how the gotcha was stamped (a test, or a future path that threads
      its own run_id through harvest). In the cheap loop the gotchas are written
      by run_pipeline's internal harvest with NO run_id (stamped ""), so this
      branch does not match there — the window rule below is what actually runs.
    - created_at window fallback: an entry stamped with a DIFFERENT non-empty
      run_id is treated as not-new; an entry with no run_id is new iff its
      first_seen / created_at is at or after ``window_start`` (the prior capture's
      wall-clock time). This window rule drives cheap-mode attribution.
    """
    if run_id and entry.run_id == run_id:
        return True
    if entry.run_id:
        # Stamped with a different run — not new this run.
        return False
    if window_start is None:
        return False
    meta = entry.metadata
    first_seen_raw = meta.get("first_seen")
    stamp: datetime | None = None
    if isinstance(first_seen_raw, str):
        try:
            stamp = datetime.fromisoformat(first_seen_raw)
        except ValueError:
            stamp = None
    if stamp is None:
        stamp = entry.created_at
    return stamp >= window_start


def capture_run_snapshot(
    root: Path,
    probe_query: str,
    prior: RunSnapshot | None = None,
    *,
    run_id: str = "",
    window_start: datetime | None = None,
) -> RunSnapshot:
    """Read a project root purely and return a ``RunSnapshot``. NEVER raises.

    Reads (each guarded):
      - latest MemoryKind.RUN entry -> artifacts_changed
      - get_gotchas() -> new vs re-encountered split (run_id-first, window fallback)
      - search(probe_query) -> mem_hits
      - run_verify(load_state(root), root) -> pass/fail/skip counts
      - build_context_prefix(root, store, probe_query) -> prefix_tokens + layers_present

    Args:
        root:        Project root to read.
        probe_query: Fixed FTS5 probe forwarded to search + prefix assembly.
        prior:       The previous run's snapshot; sets run_index and the gotcha
                     created_at window. None => run_index 0, no window.
        run_id:      The run_id to attribute *new* gotchas to (run_id-first rule).
                     In the cheap loop, harvested gotchas carry no run_id, so this
                     does not match and attribution falls to the window below.
        window_start: Prior capture's wall-clock time — the attribution window for
                     gotchas with no run_id stamp. This is the rule that actually
                     fires in cheap mode.
    """
    run_index = (prior.run_index + 1) if prior is not None else 0

    try:
        store = MemoryStore(root=root)
    except Exception:
        return _zeroed_snapshot(run_index, run_id)

    try:
        # ── artifacts_changed from the latest RUN journal entry ──────────────
        artifacts_changed = 0
        try:
            run_entries = store.get_by_kind(MemoryKind.RUN, limit=1)
            if run_entries:
                changed = run_entries[0].metadata.get("artifacts_changed")
                if isinstance(changed, list):
                    artifacts_changed = len(changed)
                elif isinstance(changed, int):
                    artifacts_changed = changed
        except Exception:
            artifacts_changed = 0

        # ── gotcha new-vs-reencounter split ──────────────────────────────────
        new_gotchas = 0
        reencountered_gotchas = 0
        try:
            for g in store.get_gotchas():
                if _is_new_gotcha(g, run_id, window_start):
                    new_gotchas += 1
                else:
                    # Any gotcha not new this run was carried over — a re-encounter.
                    reencountered_gotchas += 1
        except Exception:
            new_gotchas = 0
            reencountered_gotchas = 0

        # ── mem_hits from a probe search ─────────────────────────────────────
        mem_hits = 0
        try:
            mem_hits = len(store.search(probe_query)) if probe_query else 0
        except Exception:
            mem_hits = 0

        # ── verify pass/fail/skip ────────────────────────────────────────────
        verify_pass = verify_fail = verify_skip = 0
        try:
            for r in run_verify(load_state(root), root):
                if r.status == "pass":
                    verify_pass += 1
                elif r.status == "fail":
                    verify_fail += 1
                else:
                    verify_skip += 1
        except Exception:
            verify_pass = verify_fail = verify_skip = 0

        # ── prefix enrichment ────────────────────────────────────────────────
        prefix_tokens = 0
        layers: list[str] = []
        try:
            prefix = build_context_prefix(root, store, probe_query)
            prefix_tokens = len(prefix) // _CHARS_PER_TOKEN
            for heading in _LAYER_HEADINGS:
                if heading in prefix:
                    layers.append(heading)
            if any(marker in prefix for marker in _PACK_MARKERS):
                layers.append("<pack>")
        except Exception:
            prefix_tokens = 0
            layers = []

        snap = RunSnapshot(
            run_index=run_index,
            run_id=run_id,
            artifacts_changed=artifacts_changed,
            new_gotchas=new_gotchas,
            reencountered_gotchas=reencountered_gotchas,
            verify_pass=verify_pass,
            verify_fail=verify_fail,
            verify_skip=verify_skip,
            prefix_tokens=prefix_tokens,
            mem_hits=mem_hits,
            layers_present=tuple(layers),
        )
        return snap
    except Exception:
        return _zeroed_snapshot(run_index, run_id)
    finally:
        with contextlib.suppress(Exception):
            store.close()
