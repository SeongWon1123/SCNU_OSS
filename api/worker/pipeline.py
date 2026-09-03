"""Scan pipeline — SPEC §4.2:153 step order, own tx per step.

Phase 2-a: preflight + clone are real (worker.preflight / worker.clone, unlock per
PROMPTS.md:82); gitleaks..upload remain simulated until Phase 2-b. This file is a
locked file (AGENTS.md 잠금 파일) — edited only under that unlock.
"""

import time
from datetime import UTC, datetime
from typing import Any

from app.db import SessionLocal
from app.models import Scan
from worker import clone as clone_mod
from worker import preflight as preflight_mod
from worker.preflight import PreflightResult, RejectedScan, ScanFailure

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

RATE_LIMIT_RETRY_SECONDS = 60

ScanId = str | int


def _rate_limit_sleep() -> None:
    time.sleep(RATE_LIMIT_RETRY_SECONDS)


def _run_preflight(owner: str, repo: str) -> PreflightResult:
    """§4.3:160 — one automatic retry 60s after a GitHub rate limit."""
    try:
        return preflight_mod.run_preflight(owner, repo)
    except preflight_mod.RetryableGitHubRateLimit:
        _rate_limit_sleep()
    try:
        return preflight_mod.run_preflight(owner, repo)
    except preflight_mod.RetryableGitHubRateLimit as exc:
        raise ScanFailure("GitHub API 한도에 도달했습니다. 잠시 후 다시 시도하세요") from exc


def _finish(scan_id: ScanId, status: str, error: str | None) -> None:
    with SessionLocal() as session:
        scan = session.get(Scan, scan_id)
        if scan is None:
            return
        scan.status = status
        scan.error = error
        scan.finished_at = datetime.now(UTC)
        session.commit()


def run_scan(scan_id: ScanId) -> None:
    with SessionLocal() as session:
        scan = session.get(Scan, scan_id)
        if scan is None:
            return
        owner, repo, repo_url = scan.owner, scan.repo, scan.repo_url

    for i, step in enumerate(STEPS):
        row_patch: dict[str, Any] = {}
        meta_patch: dict[str, Any] = {}
        if step == "preflight":
            try:
                pf = _run_preflight(owner, repo)
            except RejectedScan as exc:
                _finish(scan_id, "rejected", str(exc))
                return
            except ScanFailure as exc:
                _finish(scan_id, "failed", str(exc))
                return
            row_patch = {"commit_sha": pf.commit_sha, "default_branch": pf.default_branch}
        elif step == "clone":
            try:
                stripped = clone_mod.clone_repo(repo_url, str(scan_id))
            except RejectedScan as exc:
                _finish(scan_id, "rejected", str(exc))
                return
            except ScanFailure as exc:
                _finish(scan_id, "failed", str(exc))
                return
            meta_patch = {"stripped_files": stripped}
        else:
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
            meta.update(meta_patch)
            scan.meta = meta
            for key, value in row_patch.items():
                setattr(scan, key, value)
            session.commit()
