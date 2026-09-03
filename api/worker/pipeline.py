"""Simulated scan pipeline — SPEC §4.2:153 step order, 0.3s per step, own tx per step.

This file is Phase-1-created and then locked (AGENTS.md 잠금 파일).
"""

import time
from datetime import UTC, datetime

from app.db import SessionLocal
from app.models import Scan

STEPS = [
    "preflight",
    "clone",
    "gitleaks",
    "semgrep",
    "manifest",
    "scoring",
    "explain",
    "policy",
    "upload",
    "done",
]

ScanId = str | int


def run_scan(scan_id: ScanId) -> None:
    for i, step in enumerate(STEPS):
        time.sleep(0.3)
        # Own transaction per step so progress survives a mid-scan restart.
        with SessionLocal() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                return
            meta = dict(scan.meta or {})
            if step == "done":
                meta["progress"] = {"step": step, "pct": 100}
                scan.status = "done"
                scan.finished_at = datetime.now(UTC)
            else:
                meta["progress"] = {"step": step, "pct": int(i / len(STEPS) * 100)}
            scan.meta = meta
            session.commit()
