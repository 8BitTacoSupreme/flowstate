"""Verify — pure-Python runnable checks against eval-fixture acceptance gates.

No LLM calls. No flowstate.bridge import. Reads every .planning/fixtures/*.json,
runs a bounded checker registry (real mechanical checks for checkable gates,
explicit SKIP for natural-language / unverifiable gates), and returns results.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from flowstate.state import FlowStateModel

logger = logging.getLogger(__name__)

# ReDoS-safe: bounded digit quantifier {1,3}, no backtracking groups.
# Matches the context.py L189 gate text: "Test coverage meets or exceeds {N}% as required."
_COVERAGE_RE = re.compile(r"coverage meets or exceeds (\d{1,3})%", re.IGNORECASE)


@dataclass(frozen=True)
class VerifyResult:
    """Immutable result for a single gate check — mirrors doctor.py Diagnosis shape."""

    gate: str
    status: Literal["pass", "fail", "skip"]
    message: str
    fixture: str  # basename of the fixture file the gate came from


def _parse_coverage_rate(root: Path) -> float | None:
    """Return line-rate (0.0-1.0) from coverage.xml, or None if absent/malformed.

    Reads the Cobertura-format ``line-rate`` attribute from the root element.
    Never shells out; never uses the ``coverage`` package.  Returns None when
    the file is absent, malformed, or missing the attribute.
    """
    cov_xml = root / "coverage.xml"
    if not cov_xml.exists():
        return None
    try:
        tree = ET.parse(str(cov_xml))
        rate = tree.getroot().get("line-rate")
        if rate is None:
            return None
        return float(rate)
    except Exception:
        return None


def _check_artifact_integrity(state: FlowStateModel, root: Path) -> list[VerifyResult]:
    """Backbone check: every install_manifest entry with a checksum must exist and be non-empty.

    Entries with checksum=None (e.g. memory.db) are mutable files and are excluded.
    Runs once per verify regardless of fixture gate text.
    """
    results: list[VerifyResult] = []
    for entry in state.install_manifest:
        if entry.checksum is None:
            continue
        path = root / entry.path
        if not path.exists():
            results.append(
                VerifyResult(
                    gate="produced-artifact-integrity",
                    status="fail",
                    message=f"Produced artifact missing: {entry.path}",
                    fixture="(manifest)",
                )
            )
        elif path.is_file() and path.stat().st_size == 0:
            results.append(
                VerifyResult(
                    gate="produced-artifact-integrity",
                    status="fail",
                    message=f"Produced artifact empty: {entry.path}",
                    fixture="(manifest)",
                )
            )
    return results


def _check_coverage_gate(gate: str, root: Path, fixture_name: str) -> VerifyResult:
    """Evaluate a coverage-threshold acceptance gate against coverage.xml.

    Returns PASS/FAIL when coverage.xml is present; SKIP when no report exists.
    The caller is responsible for only invoking this when _COVERAGE_RE matches.
    """
    match = _COVERAGE_RE.search(gate)
    required_pct = int(match.group(1))  # type: ignore[union-attr]
    rate = _parse_coverage_rate(root)
    if rate is None:
        return VerifyResult(
            gate=gate,
            status="skip",
            message="no coverage report found (coverage.xml absent)",
            fixture=fixture_name,
        )
    actual_pct = rate * 100
    if actual_pct >= required_pct:
        return VerifyResult(
            gate=gate,
            status="pass",
            message=f"coverage {actual_pct:.1f}% >= {required_pct}%",
            fixture=fixture_name,
        )
    return VerifyResult(
        gate=gate,
        status="fail",
        message=f"coverage {actual_pct:.1f}% < {required_pct}%",
        fixture=fixture_name,
    )


def run_verify(state: FlowStateModel, root: Path) -> list[VerifyResult]:
    """Run every mechanical check and return results. Never raises.

    Reads every .planning/fixtures/*.json (sorted), runs the bounded checker registry:
    - Backbone artifact-integrity check runs unconditionally (once per call).
    - Coverage-threshold gate: real PASS/FAIL/SKIP based on coverage.xml.
    - All other acceptance_gates and all forbidden_actions: explicit SKIP with reason.
    - Malformed fixture JSON: skip that fixture with a warning, never raise.
    """
    results: list[VerifyResult] = []

    # ── Backbone: produced-artifact integrity (always runs, fixture-independent) ──
    try:
        results.extend(_check_artifact_integrity(state, root))
    except Exception as e:
        logger.exception("artifact integrity check raised")
        results.append(
            VerifyResult(
                gate="produced-artifact-integrity",
                status="skip",
                message=f"integrity check could not run: {e}",
                fixture="(manifest)",
            )
        )

    # ── Per-fixture gate evaluation ────────────────────────────────────────────
    fixtures_dir = root / ".planning" / "fixtures"
    if not fixtures_dir.is_dir():
        return results

    for fixture_path in sorted(fixtures_dir.glob("*.json")):
        try:
            raw = fixture_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            acceptance_gates: list[str] = data.get("acceptance_gates") or []
            forbidden_actions: list[str] = data.get("forbidden_actions") or []
            fixture_name = fixture_path.name

            for gate in acceptance_gates:
                if _COVERAGE_RE.search(gate):
                    results.append(_check_coverage_gate(gate, root, fixture_name))
                else:
                    results.append(
                        VerifyResult(
                            gate=gate,
                            status="skip",
                            message="not mechanically verifiable (manual gate)",
                            fixture=fixture_name,
                        )
                    )

            for action in forbidden_actions:
                results.append(
                    VerifyResult(
                        gate=action,
                        status="skip",
                        message="not mechanically verifiable (forbidden action)",
                        fixture=fixture_name,
                    )
                )

        except Exception as e:
            logger.warning("skipping malformed fixture %s: %s", fixture_path.name, e)
            results.append(
                VerifyResult(
                    gate=fixture_path.name,
                    status="skip",
                    message=f"malformed fixture skipped: {e}",
                    fixture=fixture_path.name,
                )
            )

    return results
