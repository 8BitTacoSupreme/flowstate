"""Gotchas accumulator — pure-Python, no bridge/LLM dependency.

Captures structured failure signals from four sources (doctor diagnoses, executor
step failures, verifier gaps, plan-checker findings) into memory.db as
MemoryKind.INSIGHT entries tagged ["gotcha", "<source>"].

Deduplication is signature-based: _normalize() strips volatile tokens (paths,
timestamps, run_ids, digit runs) so the same logical failure always produces
the same sha256[:16] signature regardless of path/line-number variance.

Re-encounters increment metadata["count"] and refresh metadata["last_seen"]
via MemoryStore.update() — the memories_au AFTER UPDATE trigger keeps FTS
in sync automatically.

.planning/GOTCHAS.md is a derived mirror of memory.db; it is rewritten on
every capture_gotcha call. It is NEVER the source of truth.

All public entry points (capture_gotcha, harvest_planning_gotchas,
_rewrite_gotchas_md) are self-contained never-raises (Phase-6 WR-01).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from flowstate.memory import MemoryEntry, MemoryKind, MemoryStore

# Maximum bytes to read from a single artifact before truncating (anti-DoS).
_MAX_READ_BYTES = 100_000


def _new_id() -> str:
    """Generate a 12-char hex ID matching MemoryEntry.create() convention."""
    from uuid import uuid4

    return uuid4().hex[:12]


def _normalize(message: str) -> str:
    """Strip volatile tokens so the same logical failure produces the same signature.

    Substitution order is load-bearing:
      1. Absolute/relative paths → basename  (before digit replacement clobbers separators)
      2. ISO timestamps → <ts>              (before digit runs swallow the digits)
      3. 12-hex run_ids → <id>              (before digit runs swallow hex digits)
      4. Remaining digit runs → <n>
      5. Collapse whitespace + strip

    Regexes are bounded and anchored to stay ReDoS-safe (no nested quantifiers).
    """
    # 1. Absolute paths (/foo/bar/baz.py) → basename (baz.py)
    #    Run BEFORE lowercasing so Path.name works on original mixed-case paths.
    #    Anchored at word boundary after the replacement; no nested groups.
    s = re.sub(r"/[^\s/][^\s]*", lambda m: "/" + Path(m.group()).name, message)

    s = s.lower()

    # 2. ISO timestamps — YYYY-MM-DDThh:mm:ss with optional fractional seconds
    #    and optional timezone offset. [Tt] handles case after lower().
    #    Anchored pattern, no backtracking risk.
    s = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|[Zz])?\b",
        "<ts>",
        s,
    )

    # 3. 12-character lowercase hex run_ids (e.g. abc123def456).
    #    Word-boundary anchored; exactly 12 hex chars, not 11 or 13.
    s = re.sub(r"\b[0-9a-f]{12}\b", "<id>", s)

    # 4. Remaining digit runs → <n>
    s = re.sub(r"\b\d+\b", "<n>", s)

    # 5. Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def _signature(source: str, message: str) -> str:
    """Return a 16-char hex signature for (source, message).

    sha256(source + "|" + _normalize(message))[:16].
    Source is included so the same message from different sources produces
    different signatures (doctor vs verifier treating identical text differently).
    """
    raw = source + "|" + _normalize(message)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def capture_gotcha(
    memory: MemoryStore,
    *,
    source: str,
    message: str,
    root: Path,
    severity: str = "warning",
    run_id: str = "",
    timestamp: datetime | None = None,
) -> None:
    """Capture a failure signal into memory.db as a deduplicated INSIGHT entry.

    First occurrence: add new entry (count=1, first_seen=last_seen=now).
    Re-encounter: update existing entry (last_seen=now, count+=1, first_seen preserved).

    Wraps the entire body in try/except — self-contained never-raises (Phase-6 WR-01).
    Calls _rewrite_gotchas_md after a successful store operation.
    """
    try:
        ts = timestamp or datetime.now(UTC)
        sig = _signature(source, message)

        # --- dedup: scan existing INSIGHT+gotcha entries for a matching signature ---
        existing_entries = memory.get_by_kind(MemoryKind.INSIGHT, limit=500)
        existing: MemoryEntry | None = None
        for entry in existing_entries:
            if "gotcha" in entry.tags and entry.metadata.get("signature") == sig:
                existing = entry
                break

        if existing is not None:
            # Re-encounter: update last_seen and increment count
            existing.metadata["last_seen"] = ts.isoformat()
            existing.metadata["count"] = int(existing.metadata.get("count", 1)) + 1
            memory.update(existing)
        else:
            # First occurrence: insert new entry
            new_entry = MemoryEntry(
                id=_new_id(),
                kind=MemoryKind.INSIGHT,
                content=message,
                summary=f"[{source}] {message[:80]}",
                source=source,
                tags=["gotcha", source],
                metadata={
                    "signature": sig,
                    "source": source,
                    "severity": severity,
                    "first_seen": ts.isoformat(),
                    "last_seen": ts.isoformat(),
                    "count": 1,
                },
                created_at=ts,
                run_id=run_id,
            )
            memory.add(new_entry)

        _rewrite_gotchas_md(root, memory)
    except Exception:
        return  # never raise into caller (Phase-6 WR-01)


def _rewrite_gotchas_md(root: Path, memory: MemoryStore) -> None:
    """Rewrite .planning/GOTCHAS.md from canonical memory.db. Never raises.

    Sorted by (count desc, last_seen desc). This file is a derived mirror —
    memory.db is the source of truth. Never raises (swallows all errors).
    """
    try:
        all_entries = memory.get_by_kind(MemoryKind.INSIGHT, limit=1000)
        gotchas = [e for e in all_entries if "gotcha" in e.tags]

        # Sort: count desc, then last_seen desc
        gotchas.sort(
            key=lambda e: (
                -int(e.metadata.get("count", 1)),
                e.metadata.get("last_seen", "") or "",
            ),
            reverse=False,
        )

        lines: list[str] = [
            "# GOTCHAS\n\n",
            "> Derived mirror of memory.db — do not edit manually. "
            "Rewritten by `capture_gotcha` on every update.\n\n",
        ]

        if not gotchas:
            lines.append("_No gotchas recorded yet._\n")
        else:
            for entry in gotchas:
                meta = entry.metadata
                lines.append(f"## [{meta.get('source', '')}] {entry.summary}\n\n")
                lines.append(f"- **severity:** {meta.get('severity', 'warning')}\n")
                lines.append(f"- **first seen:** {meta.get('first_seen', '')}\n")
                lines.append(f"- **last seen:** {meta.get('last_seen', '')}\n")
                lines.append(f"- **count:** {meta.get('count', 1)}\n")
                lines.append(f"- **signature:** `{meta.get('signature', '')}`\n\n")
                lines.append(f"{entry.content.strip()}\n\n")
                lines.append("---\n\n")

        gotchas_md = root / ".planning" / "GOTCHAS.md"
        gotchas_md.parent.mkdir(parents=True, exist_ok=True)
        gotchas_md.write_text("".join(lines))
    except Exception:
        pass  # mirror write failure must never break the pipeline


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML-like frontmatter between leading '---' delimiters. No PyYAML.

    Returns {} when the first non-empty line is not '---'.
    Only handles simple key: value pairs (no nesting, no lists).
    """
    lines = text.splitlines()
    # Find first non-empty line
    start = 0
    for i, line in enumerate(lines):
        if line.strip():
            start = i
            break
    else:
        return {}

    if lines[start].strip() != "---":
        return {}

    result: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def harvest_planning_gotchas(memory: MemoryStore, root: Path) -> None:
    """Harvest gotchas from GSD planning artifacts. Best-effort, never raises.

    Sources:
      - .planning/phases/*/*-VERIFICATION.md: frontmatter status + gaps sections
        → source="verifier", severity="error"
      - .planning/phases/*/*-REVIEW.md: BLOCKER/HIGH/MEDIUM findings
        → source="plan-checker", severity="error" for BLOCKER/HIGH, "warning" for MEDIUM

    Bounded reads (cap at _MAX_READ_BYTES). ReDoS-safe regex (no nested quantifiers).
    Wraps the entire body in try/except — self-contained never-raises.
    """
    try:
        phases_dir = root / ".planning" / "phases"
        if not phases_dir.exists():
            return

        # --- VERIFICATION.md files ---
        _harvest_verification_files(memory, root, phases_dir)

        # --- REVIEW.md files ---
        _harvest_review_files(memory, root, phases_dir)

    except Exception:
        return  # never raise into pipeline


def _harvest_verification_files(memory: MemoryStore, root: Path, phases_dir: Path) -> None:
    """Harvest gotchas from *-VERIFICATION.md files. Never raises."""
    try:
        for vfile in phases_dir.glob("*/*-VERIFICATION.md"):
            try:
                _harvest_one_verification(memory, root, vfile)
            except Exception:
                continue  # skip malformed file, don't abort harvest
    except Exception:
        pass


def _harvest_one_verification(memory: MemoryStore, root: Path, vfile: Path) -> None:
    """Parse one VERIFICATION.md and capture gotchas. Never raises."""
    try:
        raw = vfile.read_bytes()[:_MAX_READ_BYTES]
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return

        fm = _parse_frontmatter(text)
        status = fm.get("status", "").lower()

        # Determine if this verification represents a failure/gap
        failing_statuses = {"failed", "blocked", "paused", "drafted"}
        # "passed", "complete", "verified" are terminal-success
        terminal_ok = {"passed", "complete", "verified"}

        has_failure = status in failing_statuses or (status not in terminal_ok and status != "")

        # Also check for a gaps/must-haves section in the body
        gaps_pattern = re.compile(
            r"^#+\s*(gaps?|must.haves?|failures?|issues?)", re.IGNORECASE | re.MULTILINE
        )
        has_gaps_section = bool(gaps_pattern.search(text))

        if not has_failure and not has_gaps_section:
            return

        # Capture the status itself as a gotcha if failing
        if has_failure and status:
            msg = f"verification {vfile.name} status: {status}"
            capture_gotcha(memory, source="verifier", message=msg, root=root, severity="error")

        # Capture individual gap lines from gaps/must-haves sections
        if has_gaps_section:
            _capture_gap_lines(memory, root, text, vfile.name)

    except Exception:
        pass


def _capture_gap_lines(memory: MemoryStore, root: Path, text: str, filename: str) -> None:
    """Extract and capture individual gap lines from a verification file body."""
    try:
        # Find lines that look like gap items (bullet points or numbered items in gaps sections)
        in_gaps = False
        gaps_header = re.compile(r"^#+\s*(gaps?|must.haves?|failures?|issues?)", re.IGNORECASE)
        any_header = re.compile(r"^#+\s+\S", re.MULTILINE)
        bullet = re.compile(r"^\s*[-*]\s+(.+)$")

        lines = text.splitlines()
        for line in lines[:500]:  # bounded line scan
            if gaps_header.match(line):
                in_gaps = True
                continue
            if in_gaps and any_header.match(line):
                in_gaps = False
                continue
            if in_gaps:
                m = bullet.match(line)
                if m:
                    gap_text = m.group(1).strip()
                    if gap_text:
                        msg = f"gap in {filename}: {gap_text}"
                        capture_gotcha(
                            memory,
                            source="verifier",
                            message=msg,
                            root=root,
                            severity="error",
                        )
    except Exception:
        pass


def _harvest_review_files(memory: MemoryStore, root: Path, phases_dir: Path) -> None:
    """Harvest gotchas from *-REVIEW.md files. Never raises."""
    try:
        for rfile in phases_dir.glob("*/*-REVIEW.md"):
            try:
                _harvest_one_review(memory, root, rfile)
            except Exception:
                continue
    except Exception:
        pass


_SEVERITY_RE = re.compile(
    r"^\s*(?:[*#\-]+\s*)?(?:severity[:\s]+)?(BLOCKER|HIGH|MEDIUM)\b",
    re.IGNORECASE,
)


def _harvest_one_review(memory: MemoryStore, root: Path, rfile: Path) -> None:
    """Parse one REVIEW.md and capture BLOCKER/HIGH/MEDIUM findings. Never raises."""
    try:
        raw = rfile.read_bytes()[:_MAX_READ_BYTES]
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            return

        lines = text.splitlines()
        for line in lines[:2000]:  # bounded scan
            m = _SEVERITY_RE.match(line)
            if not m:
                continue
            level = m.group(1).upper()
            if level not in {"BLOCKER", "HIGH", "MEDIUM"}:
                continue

            # Use the full line as the message (trimmed to reasonable length)
            finding = line.strip()[:200]
            severity = "error" if level in {"BLOCKER", "HIGH"} else "warning"
            capture_gotcha(
                memory,
                source="plan-checker",
                message=f"[{level}] {finding} (from {rfile.name})",
                root=root,
                severity=severity,
            )
    except Exception:
        pass
