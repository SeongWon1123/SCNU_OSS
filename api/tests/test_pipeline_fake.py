"""Fake-pipeline integration — sample/positive·negative as LOCAL bare repos.

Preflight is mocked (no GitHub API, PROMPTS.md:86); clone, gitleaks, semgrep and
manifest run for real against the local fixture — zero network, zero registry.
Todo 13 selects this module with `-k isolation` inside an internal-network
container. Per-rule presence only; NO total-count assertion (S2).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Finding, Scan
from tests.test_clone_hardening import _bare, _commit_push
from worker import clone
from worker.pipeline import run_scan
from worker.preflight import PreflightResult, ScanFailure
from worker.scanners import gitleaks, semgrep

SAMPLE_BASES = ("/repo/sample", str(Path(__file__).resolve().parents[2] / "sample"))
REG_RULES = ("R1", "R2", "R3", "R5", "R6", "R7")


@pytest.fixture(autouse=True)
def _scan_root():
    """The api test container has no /scan tmpfs (worker-only); create and clean it."""
    os.makedirs(clone.SCAN_ROOT, exist_ok=True)
    yield
    for entry in Path(clone.SCAN_ROOT).iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink()


def _sample_dir(name: str) -> Path:
    for base in SAMPLE_BASES:
        candidate = Path(base) / name
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"sample/{name} not found (looked in {SAMPLE_BASES})")


def _bare_from_sample(tmp_path: Path, name: str, sample: str) -> str:
    bare, work = _bare(tmp_path, name)
    shutil.copytree(_sample_dir(sample), work, dirs_exist_ok=True)
    _commit_push(work, bare)
    return bare


def _fake_preflight(monkeypatch) -> None:
    monkeypatch.setattr(
        "worker.pipeline._run_preflight",
        lambda owner, repo: PreflightResult(
            size_kb=1, default_branch="main", commit_sha="b" * 40, file_count=7
        ),
    )


def _insert_scan(repo_url: str, repo: str) -> str:
    scan = Scan(repo_url=repo_url, owner="local", repo=repo, owner_token="tok-fake")
    with SessionLocal() as session:
        session.add(scan)
        session.commit()
        return str(scan.id)


def _findings(scan_id: str) -> list[Finding]:
    with SessionLocal() as session:
        return list(session.scalars(select(Finding).where(Finding.scan_id == scan_id)))


def test_full_pipeline_fake_positive(tmp_path, monkeypatch):
    _fake_preflight(monkeypatch)
    bare = _bare_from_sample(tmp_path, "pos", "positive")
    scan_id = _insert_scan(bare, "positive")

    run_scan(scan_id)

    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None
        assert row.status == "done"
        assert row.score is None  # scoring is the D6 stub until Phase 3
        counts = dict(row.meta["counts"])
    findings = _findings(scan_id)
    present = {f.reg_rule for f in findings if f.axis == "regulation"}
    for rule in REG_RULES:
        assert rule in present, f"{rule} missing from {sorted(present)}"
        print(f"{rule}: {sum(1 for f in findings if f.reg_rule == rule)}")
    assert counts["regulation"] == sum(1 for f in findings if f.axis == "regulation")


def test_full_pipeline_fake_negative_regulation_zero(tmp_path, monkeypatch):
    _fake_preflight(monkeypatch)
    bare = _bare_from_sample(tmp_path, "neg", "negative")
    scan_id = _insert_scan(bare, "negative")

    run_scan(scan_id)

    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None
        assert row.status == "done"
    assert [f for f in _findings(scan_id) if f.axis == "regulation"] == []


def _mock_semgrep_rc(monkeypatch, rc: int) -> None:
    payload = json.dumps({"version": "1.176.0", "results": []})
    monkeypatch.setattr(
        "worker.scanners.semgrep.subprocess.run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, rc, stdout=payload, stderr=""),
    )


def test_semgrep_exit_1_is_success(monkeypatch):
    """수정 #5 regression guard: semgrep exit 1 (findings present) is NOT a failure."""
    scan_id = "semgrep-rc1"
    os.makedirs(clone.scan_path(scan_id), exist_ok=True)
    _mock_semgrep_rc(monkeypatch, 1)

    result = semgrep.run(scan_id)

    assert result.findings == []


def test_semgrep_exit_2_is_failure(monkeypatch):
    scan_id = "semgrep-rc2"
    os.makedirs(clone.scan_path(scan_id), exist_ok=True)
    _mock_semgrep_rc(monkeypatch, 2)

    with pytest.raises(ScanFailure):
        semgrep.run(scan_id)


def test_semgrep_timeout_maps_to_failed_message(monkeypatch):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=120)

    monkeypatch.setattr("worker.scanners.semgrep.subprocess.run", slow)

    with pytest.raises(ScanFailure) as ei:
        semgrep.run("t")
    assert str(ei.value) == "분석 시간 초과"


def test_gitleaks_timeout_maps_to_failed_message(monkeypatch):
    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

    monkeypatch.setattr("worker.scanners.gitleaks.subprocess.run", slow)

    with pytest.raises(ScanFailure) as ei:
        gitleaks.run("t")
    assert str(ei.value) == "분석 시간 초과"


def test_gitleaks_collapse_same_ruleid_and_masked_snippet():
    entries = [
        {
            "RuleID": "aws-key",
            "Secret": f"sk-secret-{i}",
            "File": f"f{i}.js",
            "StartLine": i,
            "EndLine": i,
        }
        for i in range(7)
    ] + [
        {
            "RuleID": "stripe-key",
            "Secret": "pk-live-999",
            "File": "pay.js",
            "StartLine": 1,
            "EndLine": 1,
        }
    ]

    findings = gitleaks._parse_report(entries)

    assert len(findings) == 2  # 7 same-RuleID occurrences collapse to 1 + 1 other
    aws = next(f for f in findings if f["rule_id"] == "gitleaks:aws-key")
    assert aws["weight"] == 15
    assert aws["severity"] == "critical"
    assert aws["snippet"] == "sk****"
    dumped = json.dumps(findings)
    assert "sk-secret" not in dumped and "pk-live" not in dumped  # raw secrets never stored


def test_gitleaks_report_deleted_after_run_scan(tmp_path, monkeypatch):
    _fake_preflight(monkeypatch)
    bare = _bare_from_sample(tmp_path, "report", "positive")
    scan_id = _insert_scan(bare, "positive")

    run_scan(scan_id)

    assert not os.path.exists(os.path.join(clone.scan_path(scan_id), gitleaks.REPORT_NAME))
    assert not os.path.exists(clone.scan_path(scan_id))


def test_isolation_local_bare_repo_zero_registry(tmp_path, monkeypatch):
    """`-k isolation` target (todo 13): run_scan direct on a local bare-repo fixture —
    preflight mocked away, clone/gitleaks/semgrep/manifest real, no network at all."""
    _fake_preflight(monkeypatch)
    bare = _bare_from_sample(tmp_path, "iso", "positive")
    scan_id = _insert_scan(bare, "positive")

    run_scan(scan_id)

    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None
        assert row.status == "done"
    assert any(f.reg_rule in REG_RULES for f in _findings(scan_id))
