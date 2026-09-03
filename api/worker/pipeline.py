"""Scan pipeline — SPEC §4.2:153 step order, own tx per step.

Phase 2-b: preflight, clone, gitleaks, semgrep and manifest are real; scoring is
the Phase 3 pure function (worker.scoring.compute, dynamic import per D6);
explain/policy/upload remain simulated sleeps. The pipeline owns the §5.2
scan-level `rm -rf /scan/<id>` in finally.
This file is a locked file (AGENTS.md 잠금 파일) — edited under the PROMPTS.md:96
unlock declared in the PR body.
"""

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Finding, Scan
from worker import catalog as catalog_mod
from worker import clone as clone_mod
from worker import preflight as preflight_mod
from worker.preflight import PreflightResult, RejectedScan, ScanFailure
from worker.scanners import gitleaks as gitleaks_mod
from worker.scanners import manifest as manifest_mod
from worker.scanners import semgrep as semgrep_mod

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
SIMULATED_STEP_SECONDS = 0.3

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


def _compute_score(scan_id: ScanId) -> dict[str, Any] | None:
    """Phase 3 (todo 14) — the D6 dynamic import now resolves. Contract:
    compute(findings, catalog) → {"score", "grade", "detail"} (SPEC §6)."""
    try:
        from worker.scoring import compute
    except ImportError:
        return None
    with SessionLocal() as session:
        rows = list(session.scalars(select(Finding).where(Finding.scan_id == scan_id)))
        findings = [
            {
                "axis": row.axis,
                "scope": row.scope,
                "rule_id": row.rule_id,
                "reg_rule": row.reg_rule,
                "severity": row.severity,
                "confidence": row.confidence,
                "file_path": row.file_path,
                "snippet": row.snippet,
                "weight": row.weight,
            }
            for row in rows
        ]
        return compute(findings, catalog_mod.load())


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

    try:
        for i, step in enumerate(STEPS):
            row_patch: dict[str, Any] = {}
            meta_patch: dict[str, Any] = {}
            findings: list[dict[str, Any]] = []
            axis_counts: dict[str, int] = {}
            started = time.perf_counter()
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
            elif step == "gitleaks":
                result = gitleaks_mod.run(str(scan_id))
                findings = result.findings
                axis_counts = {"secrets": len(findings)}
                meta_patch = {"tools": result.tools}
            elif step == "semgrep":
                result = semgrep_mod.run(str(scan_id))
                findings = result.findings
                axis_counts = {
                    "regulation": sum(1 for f in findings if f["axis"] == "regulation"),
                    "security": sum(1 for f in findings if f["axis"] == "security"),
                }
                meta_patch = {"truncated": result.truncated, "tools": result.tools}
            elif step == "manifest":
                result = manifest_mod.run(str(scan_id))
                findings = result.findings
                axis_counts = {"regulation": sum(1 for f in findings if f["axis"] == "regulation")}
            elif step == "scoring":
                result = _compute_score(scan_id)
                if result is not None:
                    row_patch = {
                        "score": result["score"],
                        "grade": result["grade"],
                        "score_detail": result["detail"],
                    }
            else:
                time.sleep(SIMULATED_STEP_SECONDS)  # explain/policy/upload — Phase 3+
            # Own transaction per step so progress survives a mid-scan restart.
            with SessionLocal() as session:
                scan = session.get(Scan, scan_id)
                if scan is None:
                    return
                meta = dict(scan.meta or {})
                counts = dict(meta.get("counts") or {})
                for axis, delta in axis_counts.items():
                    counts[axis] = counts.get(axis, 0) + delta
                tools = {**meta.get("tools", {}), **meta_patch.pop("tools", {})}
                if counts:
                    meta["counts"] = counts
                if tools:
                    meta["tools"] = tools
                if step == "done":
                    meta["progress"] = {"step": step, "pct": 100, "counts": counts}
                    scan.status = "done"
                    scan.finished_at = datetime.now(UTC)
                else:
                    meta["progress"] = {
                        "step": step,
                        "pct": int(i / len(STEPS) * 100),
                        "counts": counts,
                    }
                meta["timings"] = {
                    **meta.get("timings", {}),
                    step: round(time.perf_counter() - started, 2),
                }
                meta.update(meta_patch)
                scan.meta = meta
                for key, value in row_patch.items():
                    setattr(scan, key, value)
                for finding in findings:
                    session.add(Finding(scan_id=scan_id, **finding))
                session.commit()
    finally:
        # §5.2 scan-level cleanup — /scan/<id> (gitleaks report included) never outlives run_scan.
        clone_mod.cleanup_scan_dir(str(scan_id))
