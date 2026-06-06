"""DX-01 verify: both quick-task SUMMARYs marked complete + audit-open shows 0 open quick tasks.

Run from repo root: python3 scripts/_dx01_verify.py
Exits 0 on success, non-zero otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

QUICK = Path(".planning/quick")
SUMMARIES = [
    QUICK / "260525-m9v-unify-memory-injection-at-orchestrator-b" / "260525-m9v-SUMMARY.md",
    QUICK / "260525-o6h-spike-confirm-claude-print-server-side-p" / "260525-o6h-SUMMARY.md",
]


def main() -> int:
    for path in SUMMARIES:
        text = path.read_text()
        if "status: complete" not in text:
            print(f"FAIL: {path} missing 'status: complete'")
            return 1

    out = subprocess.run(
        ["gsd-sdk", "query", "audit-open", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    count = json.loads(out.stdout)["counts"]["quick_tasks"]
    print(f"quick_tasks open = {count}")
    return 0 if count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
