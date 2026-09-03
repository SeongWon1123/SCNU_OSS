"""Fake-pipeline integration — sample/positive·negative as LOCAL bare repos.

Preflight is mocked (no GitHub API, PROMPTS.md:86); clone, gitleaks, semgrep and
manifest run for real against the local fixture — zero network, zero registry.
Todo 13 selects this module with `-k isolation` inside an internal-network
container. Per-rule presence only; NO total-count assertion (S2).
Todo 16: Phase 4 LLM pipeline — probe fallback units + invalid-key/explain-off
scan flows (the OpenAI SDK seam is faked hermetically; no live LLM calls — 16-B
is key-gated and BLOCKED, see .omo/evidence/repodoc-kickoff/BLOCKED-task-16.md).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Finding, Scan
from tests.test_clone_hardening import _bare, _commit_push
from worker import clone
from worker.pipeline import run_scan
from worker.preflight import PreflightResult, ScanFailure
from worker.scanners import gitleaks, semgrep

client = TestClient(app)

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


def _insert_scan(repo_url: str, repo: str, meta: dict | None = None) -> str:
    scan = Scan(
        repo_url=repo_url,
        owner="local",
        repo=repo,
        owner_token="tok-fake",
        meta=meta if meta is not None else {},
    )
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
        # Todo 14 DoD (SPEC §6): sample/positive full-pipeline scoring.
        assert row.score is not None
        detail = dict(row.score_detail or {})
        regulation_penalty = 40 - detail.get("regulation", 40)
        assert regulation_penalty == 40, f"score_detail={detail}"
        assert row.score <= 60
        assert row.grade in ("C", "D", "F")
        print(
            f"breakdown: security_penalty={40 - detail.get('security', 40)} "
            f"regulation_penalty={regulation_penalty} "
            f"license_penalty={20 - detail.get('license', 20)} "
            f"score={row.score} grade={row.grade}"
        )
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


# ---------------------------------------------------------------- Phase 4 LLM

POLICY_TITLES = (
    "처리 목적",
    "처리·보유 기간",
    "처리 항목",
    "제3자 제공",
    "위탁",
    "국외 이전",
    "파기",
    "정보주체 권리",
    "안전성 확보 조치",
    "자동 수집 장치",
    "행태정보",
    "보호책임자",
    "열람청구",
    "권익침해 구제",
    "변경",
    "자동화된 결정",
    "만 14세 미만 아동",
    "추가적 이용·제공 기준",
)


class _FakeModels:
    def __init__(self, retrieve_error: Exception | None, list_error: Exception | None):
        self._retrieve_error = retrieve_error
        self._list_error = list_error

    def retrieve(self, model: str) -> None:
        if self._retrieve_error is not None:
            raise self._retrieve_error

    def list(self) -> None:
        if self._list_error is not None:
            raise self._list_error


class _FakeOpenAI:
    """PROMPTS.md:86 — SDK seam fake; 401/404 paths simulated, no live calls."""

    instances: ClassVar[list["_FakeOpenAI"]] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.api_key = str(kwargs.get("api_key") or "")
        self.models = _FakeModels(RuntimeError("404"), None)
        _FakeOpenAI.instances.append(self)


def _patch_llm_env(monkeypatch, api_key: str, model: str) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", api_key)
    monkeypatch.setenv("OPENAI_MODEL", model)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def test_llm_probe_retrieve_error_falls_back_to_list(monkeypatch):
    """⑥ 편차 회귀: retrieve 404만으로는 LLM_ENABLED=false가 아니다(OpenRouter 대비)."""
    from worker.llm.client import LLMClient

    monkeypatch.setattr("worker.llm.client.OpenAI", _FakeOpenAI)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    assert LLMClient(_settings("sk-probe-16a", "probe-model")).probe() is True


def test_llm_probe_both_fail_disables(monkeypatch):
    from worker.llm.client import LLMClient

    class _BothFail(_FakeOpenAI):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.models = _FakeModels(RuntimeError("404"), RuntimeError("401"))

    monkeypatch.setattr("worker.llm.client.OpenAI", _BothFail)

    assert LLMClient(_settings("sk-probe-16b", "probe-model")).probe() is False


def test_invalid_key_scan_done_skipped_within_budget(tmp_path, monkeypatch):
    """16-A(a): 무효 키 스캔 → done + meta.llm.status='skipped' + findings 불변."""
    import time as time_mod

    from worker.llm import client as llm_client

    _fake_preflight(monkeypatch)
    _patch_llm_env(monkeypatch, "sk-invalid-16a", "invalid-model-16a")

    class _Unauthorized(_FakeOpenAI):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.models = _FakeModels(RuntimeError("401"), RuntimeError("401"))

    monkeypatch.setattr("worker.llm.client.OpenAI", _Unauthorized)
    bare = _bare_from_sample(tmp_path, "inv16a", "positive")
    scan_id = _insert_scan(bare, "positive", {"explain": True})

    started = time_mod.monotonic()
    run_scan(scan_id)
    elapsed = time_mod.monotonic() - started

    assert elapsed < 60
    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None and row.status == "done"
        llm = dict(row.meta["llm"])
        assert llm["status"] == "skipped"
        assert llm["calls"] == 0
        assert llm["explained"] == 0
    assert all(f.explain_ko is None for f in _findings(scan_id))
    llm_client.drop_budget(scan_id)


def test_explain_off_zero_llm_calls_and_policy_rendered(tmp_path, monkeypatch):
    """16-A(b,c): explain=false → LLM 호출 0 + 방침 18목차 + 수집 항목 3종 + 라우트."""
    from worker.llm import client as llm_client

    _fake_preflight(monkeypatch)
    _patch_llm_env(monkeypatch, "sk-never-used-16b", "never-model-16b")

    class _Forbidden(_FakeOpenAI):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            raise AssertionError("explain=false 스캔에서 LLM SDK가 생성되면 안 됩니다")

    monkeypatch.setattr("worker.llm.client.OpenAI", _Forbidden)
    bare = _bare_from_sample(tmp_path, "off16b", "positive")
    scan_id = _insert_scan(bare, "positive", {"explain": False})

    run_scan(scan_id)

    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None and row.status == "done"
        llm = dict(row.meta["llm"])
        assert llm["status"] == "explain_off"
        assert llm["calls"] == 0
        policy = row.privacy_policy_md
        notice = row.ai_notice_md
        assert row.summary_ko
        assert row.score is not None
    assert policy is not None
    for title in POLICY_TITLES:
        assert title in policy, f"목차 누락: {title}"
    assert "이메일, 전화번호, 위치정보" in policy
    assert "[서비스 설명을 입력하세요]" in policy  # README <300자 → 미호출 고정 문구
    assert notice is not None  # sample/positive는 R6 신호 보유 → AI 고지 렌더

    # 16-A(d): 토큰 있음 → text/markdown, 없음/틀림 → 404, AI 고지는 R6라 200.
    ok = client.get(f"/api/scans/{scan_id}/privacy-policy.md", params={"t": "tok-fake"})
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/markdown")
    assert ok.text == policy
    assert client.get(f"/api/scans/{scan_id}/privacy-policy.md").status_code == 404
    assert (
        client.get(f"/api/scans/{scan_id}/privacy-policy.md", params={"t": "wrong"}).status_code
        == 404
    )
    assert (
        client.get(f"/api/scans/{scan_id}/ai-notice.md", params={"t": "tok-fake"}).status_code
        == 200
    )
    llm_client.drop_budget(scan_id)


def _settings(api_key: str, model: str):
    from app.config import Settings

    return Settings(openai_api_key=api_key, openai_model=model)


def test_ai_notice_route_404_without_r6_document():
    """16-A(d): AI 고지가 없는 스캔의 ai-notice.md는 404."""
    scan = Scan(
        repo_url="https://github.com/local/nor6",
        owner="local",
        repo="nor6",
        owner_token="tok-noai",
        status="done",
        privacy_policy_md="# 방침",
        meta={},
    )
    with SessionLocal() as session:
        session.add(scan)
        session.commit()
        scan_id = str(scan.id)

    assert (
        client.get(f"/api/scans/{scan_id}/ai-notice.md", params={"t": "tok-noai"}).status_code
        == 404
    )
    assert (
        client.get(f"/api/scans/{scan_id}/privacy-policy.md", params={"t": "tok-noai"}).status_code
        == 200
    )
    unknown = "/api/scans/00000000-0000-0000-0000-000000000000/ai-notice.md"
    assert client.get(unknown, params={"t": "x"}).status_code == 404
