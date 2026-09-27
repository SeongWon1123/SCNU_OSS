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
from app.models import RateLimitHit, Scan
from worker.pipeline import run_scan
from worker.preflight import PreflightResult
from worker.scanners import ScannerResult

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


def _insert_done_scan(owner: str, repo: str, consent: bool, **extra: object) -> dict:
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
        **extra,
    )
    with Session(bind=deps.engine) as session:
        session.add(scan)
        session.commit()
        return {"id": str(scan.id), "owner": owner, "repo": repo, "token": scan.owner_token}


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
    # Phase 2-b made the scanners real (heavy binaries); this queue test stays
    # hermetic per PROMPTS.md:86 — real scanner results are covered by
    # test_pipeline_fake.py against a local bare-repo fixture.
    monkeypatch.setattr("worker.scanners.gitleaks.run", lambda scan_id: ScannerResult(findings=[]))
    monkeypatch.setattr("worker.scanners.semgrep.run", lambda scan_id: ScannerResult(findings=[]))
    monkeypatch.setattr("worker.scanners.manifest.run", lambda scan_id: ScannerResult(findings=[]))

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
    inserted = _insert_done_scan(owner, "repo", consent=True)
    r = _post(_ip(), f"https://github.com/{owner}/repo")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == inserted["id"]
    assert "owner_token" not in body


def test_force_bypasses_24h_cache():
    owner = f"t-{_uid()}"
    inserted = _insert_done_scan(owner, "repo", consent=True)
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


def test_post_persists_consent_flag():
    owner = f"t-{_uid()}"
    r = _post(_ip(), f"https://github.com/{owner}/repo", consent=True)
    assert r.status_code == 201
    created = r.json()
    full = client.get(f"/api/scans/{created['id']}?t={created['owner_token']}").json()
    assert full["consent"] is True

    owner2 = f"t-{_uid()}"
    r2 = _post(_ip(), f"https://github.com/{owner2}/repo")
    assert r2.status_code == 201
    created2 = r2.json()
    full2 = client.get(f"/api/scans/{created2['id']}?t={created2['owner_token']}").json()
    assert full2["consent"] is False


def test_get_full_includes_fix_impacts():
    from app.models import Finding

    owner = f"t-{_uid()}"
    created = _post(_ip(), f"https://github.com/{owner}/repo").json()
    with Session(bind=deps.engine) as session:
        session.add(
            Finding(
                scan_id=uuid.UUID(created["id"]),
                axis="regulation",
                scope="app",
                rule_id="semgrep:kr-r1-browser-geolocation",
                reg_rule="R1",
                severity="medium",
                confidence="medium",
                file_path="a.js",
                line_start=1,
                line_end=1,
                snippet="x",
                title_ko="t",
                weight=8,
            )
        )
        session.commit()
    full = client.get(f"/api/scans/{created['id']}?t={created['owner_token']}").json()
    impacts = {i["reg_rule"]: i["points"] for i in full["fix_impacts"]}
    assert impacts.get("R1") == 8


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


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://github.com/-x/y",
        "https://github.com/a/%2e%2e",
        "https://github.com/a/..",
        "https://github.com/a/b?x=1",
        "https://github.com/a/b c",
        "https://github.com/a/b\n",
        "https://github.com/a\x00/b",
        "https://github.com/a/" + "r" * 101,
    ],
)
def test_malformed_repo_url_rejected_422(repo_url):
    r = _post(_ip(), repo_url)
    assert r.status_code == 422
    assert r.json()["detail"] == "공개 GitHub 저장소만 지원합니다"


def test_dotted_dashed_repo_url_accepted():
    r = _post(_ip(), "https://github.com/a-b/c.d_e.git")
    assert r.status_code == 201
    created = r.json()
    full = client.get(f"/api/scans/{created['id']}?t={created['owner_token']}").json()
    assert full["repo_url"] == "https://github.com/a-b/c.d_e"
    assert (full["owner"], full["repo"]) == ("a-b", "c.d_e")


def test_non_ascii_token_is_limited_not_500():
    inserted = _insert_done_scan(f"t-{_uid()}", "repo", consent=True, privacy_policy_md="# p")
    resp = client.get(f"/api/scans/{inserted['id']}?t=%C3%A9")
    assert resp.status_code == 200
    assert resp.json()["message"] == "상세는 스캔 생성자만 볼 수 있습니다"
    md = client.get(f"/api/scans/{inserted['id']}/privacy-policy.md?t=%C3%A9")
    assert md.status_code == 404


def test_running_scan_without_token_has_no_findings():
    from app.models import Finding

    created = _post(_ip(), f"https://github.com/t-{_uid()}/repo").json()
    with Session(bind=deps.engine) as session:
        scan = session.get(Scan, uuid.UUID(created["id"]))
        scan.status = "running"
        session.add(
            Finding(
                scan_id=scan.id,
                axis="security",
                scope="app",
                rule_id="gitleaks:generic-api-key",
                severity="high",
                confidence="high",
                file_path="secret.py",
                line_start=1,
                line_end=1,
                snippet="KEY=...",
                title_ko="t",
                weight=10,
            )
        )
        session.commit()
    body = client.get(f"/api/scans/{created['id']}").json()
    assert body["status"] == "running"
    assert "findings" not in body


def test_non_consented_scan_without_token_hides_score():
    hidden = _insert_done_scan(f"t-{_uid()}", "repo", consent=False)
    body = client.get(f"/api/scans/{hidden['id']}").json()
    assert (body["score"], body["grade"], body["score_detail"]) == (None, None, None)
    assert body["status"] == "done"

    shown = _insert_done_scan(f"t-{_uid()}", "repo", consent=True)
    assert client.get(f"/api/scans/{shown['id']}").json()["score"] == 88

    full = client.get(f"/api/scans/{hidden['id']}?t={hidden['token']}").json()
    assert full["score"] == 88


def test_cache_skips_non_consented_scan():
    owner = f"t-{_uid()}"
    inserted = _insert_done_scan(owner, "repo", consent=False)
    r = _post(_ip(), f"https://github.com/{owner}/repo")
    assert r.status_code == 201
    assert r.json()["id"] != inserted["id"]
    assert "owner_token" in r.json()


@pytest.fixture()
def cap_settings():
    def _apply(**overrides: object) -> None:
        app.dependency_overrides[get_settings] = lambda: Settings(**overrides)

    yield _apply
    app.dependency_overrides.clear()


def _ip_hits(ip: str) -> int:
    with Session(bind=deps.engine) as session:
        hit = session.query(RateLimitHit).filter(RateLimitHit.ip == ip).first()
        return hit.hits if hit is not None else 0


def test_queue_cap_returns_503_before_ip_counter(cap_settings):
    cap_settings(max_queued_scans=1)
    assert _post(_ip(), f"https://github.com/t-{_uid()}/repo").status_code == 201
    ip = _ip()
    r = _post(ip, f"https://github.com/t-{_uid()}/repo")
    assert r.status_code == 503
    assert r.json()["detail"] == "지금 대기 중인 검사가 많습니다 — 잠시 후 다시 시도하세요"
    assert _ip_hits(ip) == 0


def test_global_daily_cap_returns_429_before_ip_counter(cap_settings):
    cap_settings(global_daily_scan_limit=1)
    assert _post(_ip(), f"https://github.com/t-{_uid()}/repo").status_code == 201
    ip = _ip()
    r = _post(ip, f"https://github.com/t-{_uid()}/repo")
    assert r.status_code == 429
    assert r.json()["detail"] == "오늘 서비스 전체 검사 한도에 도달했습니다 — 내일 다시 시도하세요"
    assert _ip_hits(ip) == 0


@pytest.mark.parametrize(
    ("path", "column", "filename"),
    [
        ("privacy-policy.md", "privacy_policy_md", "privacy-policy.md"),
        ("ai-notice.md", "ai_notice_md", "ai-notice.md"),
    ],
)
def test_markdown_download_headers(path, column, filename):
    inserted = _insert_done_scan(f"t-{_uid()}", "repo", consent=True, **{column: "# 문서"})
    resp = client.get(f"/api/scans/{inserted['id']}/{path}?t={inserted['token']}")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-disposition"] == f'attachment; filename="{filename}"'
    assert resp.text == "# 문서"
