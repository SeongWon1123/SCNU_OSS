"""Badge tests — SPEC.md §4.2 (Phase 7 Should): consent done 최근 1건 SVG, 없으면 not scanned."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import deps
from app.main import app
from app.models import Scan

client = TestClient(app)

GRADE_COLOR_C = "#dfb317"


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _insert_scan(owner: str, repo: str, *, consent: bool, finished_at: datetime | None = None) -> None:
    with Session(bind=deps.engine) as db:
        db.add(
            Scan(
                repo_url=f"https://github.com/{owner}/{repo}",
                owner=owner,
                repo=repo,
                owner_token="tok-" + uuid.uuid4().hex,
                consent=consent,
                status="done",
                score=60,
                grade="C",
                finished_at=finished_at or datetime.now(UTC),
            )
        )
        db.commit()


def test_badge_renders_scored_svg_for_latest_consent_done_scan():
    owner, repo = f"o-{_uid()}", "demo"
    _insert_scan(owner, repo, consent=True)
    _insert_scan(owner, repo, consent=True, finished_at=datetime.now(UTC) - timedelta(days=1))

    resp = client.get(f"/api/badge/{owner}/{repo}.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert resp.headers["cache-control"] == "max-age=300"
    body = resp.text
    assert "리포닥" in body
    assert "60 · C" in body
    assert GRADE_COLOR_C in body


def test_badge_shows_not_scanned_without_consent_done_scan():
    owner, repo = f"o-{_uid()}", "private"
    # consent=false done 스캔은 뱃지 대상에서 제외된다.
    _insert_scan(owner, repo, consent=False)

    resp = client.get(f"/api/badge/{owner}/{repo}.svg")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    body = resp.text
    assert "not scanned" in body
    assert "#9f9f9f" in body
