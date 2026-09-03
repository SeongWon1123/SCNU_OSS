"""API queue tests — SPEC.md §4.2: POST → poll → done, token-gated GET, XFF, 429, cache, force.

Each POST uses a unique X-Forwarded-For and unique owner so repeated runs are
idempotent; conftest truncates scans/findings/rate_limit_hits before each test.
"""

import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import deps
from app.config import Settings
from app.deps import get_settings
from app.main import app
from app.models import Scan
from worker.pipeline import run_scan
from worker.preflight import PreflightResult

client = TestClient(app)

_IP_SEQ = (f"192.0.2.{n}" for n in range(2, 200))


def _ip() -> str:
    return next(_IP_SEQ)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _post(ip: str, repo_url: str, **extra: object) -> object:
    return client.post(
        "/api/scans",
        json={"repo_url": repo_url, **extra},
        headers={"X-Forwarded-For": ip},
    )


def _insert_done_scan(owner: str, repo: str, consent: bool) -> dict:
    scan = Scan(
        repo_url=f"https://github.com/{owner}/{repo}",
        owner=owner,
        repo=repo,
        owner_token="tok-" + uuid.uuid4().hex,
        consent=consent,
        status="done",
        score=88,
        grade="B",
        score_detail={"security": 88},
        meta={"progress": {"step": "done", "pct": 100}, "queue_position": 0},
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    with Session(bind=deps.engine) as session:
        session.add(scan)
        session.commit()
        return {"id": str(scan.id), "owner": owner, "repo": repo}


def test_post_creates_scan_and_polls_to_done_within_10s(monkeypatch):
    # Phase 2-a made preflight/clone real (network + git); unit tests mock them
    # (PROMPTS.md:86 — no real external calls from tests).
    monkeypatch.setattr(
        "worker.preflight.run_preflight",
        lambda owner, repo: PreflightResult(
            size_kb=1, default_branch="main", commit_sha="a" * 40, file_count=3
        ),
    )
    monkeypatch.setattr("worker.clone.clone_repo", lambda url, scan_id: [])

    owner = f"t-{_uid()}"
    r = _post(_ip(), f"https://github.com/{owner}/repo")
    assert r.status_code == 201
    created = r.json()
    for key in ("id", "status", "owner_token", "queue_position"):
        assert key in created
    assert created["status"] == "queued"

    thread = threading.Thread(target=lambda: run_scan(created["id"]), daemon=True)
    thread.start()

    deadline = 10.0
    start = time.monotonic()
    final = None
    while time.monotonic() - start < deadline:
        resp = client.get(f"/api/scans/{created['id']}?t={created['owner_token']}")
        body = resp.json()
        if body.get("status") == "done":
            final = body
            break
        time.sleep(0.3)
    thread.join(timeout=5)
    assert final is not None, f"scan did not finish within {deadline}s"
    assert "owner_token" not in final
    assert final["repo_url"] == f"https://github.com/{owner}/repo"
    assert final["owner"] == owner


def test_get_without_token_returns_limited_fields():
    owner = f"t-{_uid()}"
    created = _post(_ip(), f"https://github.com/{owner}/repo").json()
    scan_id = created["id"]

    for token in ("", "wrong-token"):
        resp = client.get(f"/api/scans/{scan_id}" + (f"?t={token}" if token else ""))
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "id",
            "status",
            "score",
            "grade",
            "score_detail",
            "progress",
            "message",
        }
        assert body["message"] == "상세는 스캔 생성자만 볼 수 있습니다"
        assert "owner_token" not in body
        assert "repo_url" not in body


@pytest.fixture()
def limited_settings():
    app.dependency_overrides[get_settings] = lambda: Settings(
        daily_limit_per_ip=1, rate_limit_bypass_ips="10.10.10.10"
    )
    yield
    app.dependency_overrides.clear()


def test_daily_limit_429_and_bypass(limited_settings):
    ip = _ip()
    first = _post(ip, f"https://github.com/{_uid()}/repo")
    assert first.status_code == 201

    second = _post(ip, f"https://github.com/{_uid()}/repo")
    assert second.status_code == 429
    assert second.json()["detail"] == "오늘 스캔 요청 한도에 도달했습니다 — 내일 다시 시도하세요"

    bypassed = _post("10.10.10.10", f"https://github.com/{_uid()}/repo")
    assert bypassed.status_code == 201


def test_24h_cache_returns_existing_id_without_force():
    owner = f"t-{_uid()}"
    inserted = _insert_done_scan(owner, "repo", consent=False)
    r = _post(_ip(), f"https://github.com/{owner}/repo")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == inserted["id"]
    assert "owner_token" not in body


def test_force_bypasses_24h_cache():
    owner = f"t-{_uid()}"
    inserted = _insert_done_scan(owner, "repo", consent=False)
    r = _post(_ip(), f"https://github.com/{owner}/repo", force=True)
    assert r.status_code == 201
    assert r.json()["id"] != inserted["id"]


def test_non_github_url_rejected_422():
    r = _post(_ip(), "https://gitlab.com/x/y")
    assert r.status_code == 422
    assert r.json()["detail"] == "공개 GitHub 저장소만 지원합니다"


def test_tree_and_git_suffix_normalized():
    owner = f"t-{_uid()}"
    r1 = _post(_ip(), f"https://github.com/{owner}/repo/tree/main")
    assert r1.status_code == 201
    r2 = _post(_ip(), f"https://github.com/{owner}/repo.git")
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
    scan_id = r1.json()["id"]
    full = client.get(f"/api/scans/{scan_id}?t={r1.json()['owner_token']}").json()
    assert full["repo_url"] == f"https://github.com/{owner}/repo"


def test_recent_lists_only_consent_done_scans():
    shown = _insert_done_scan(f"t-{_uid()}", "open", consent=True)
    hidden = _insert_done_scan(f"t-{_uid()}", "closed", consent=False)

    resp = client.get("/api/scans/recent")
    assert resp.status_code == 200
    rows = resp.json()
    assert any(r["owner"] == shown["owner"] and r["repo"] == "open" for r in rows)
    assert not any(r["owner"] == hidden["owner"] for r in rows)
    shown_row = next(r for r in rows if r["owner"] == shown["owner"])
    assert set(shown_row.keys()) == {"owner", "repo", "score", "grade"}
