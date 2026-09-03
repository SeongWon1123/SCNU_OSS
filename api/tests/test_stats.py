"""Stats tests — SPEC.md §4.2 (Phase 7 Should): {scans_done, repos, last_24h} 정확 키."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import deps
from app.main import app
from app.models import Scan

client = TestClient(app)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _insert_scan(
    owner: str,
    repo: str,
    *,
    consent: bool,
    status: str,
    finished_at: datetime | None = None,
) -> None:
    with Session(bind=deps.engine) as db:
        db.add(
            Scan(
                repo_url=f"https://github.com/{owner}/{repo}",
                owner=owner,
                repo=repo,
                owner_token="tok-" + uuid.uuid4().hex,
                consent=consent,
                status=status,
                score=60 if status == "done" else None,
                grade="C" if status == "done" else None,
                finished_at=finished_at if status == "done" else None,
            )
        )
        db.commit()


def test_stats_counts_done_scans_distinct_repos_and_last_24h():
    u = _uid()
    _insert_scan(f"o-{u}", "alpha", consent=True, status="done", finished_at=datetime.now(UTC))
    _insert_scan(
        f"o-{u}",
        "beta",
        consent=False,
        status="done",
        finished_at=datetime.now(UTC) - timedelta(days=2),
    )
    _insert_scan(f"o-{u}", "gamma", consent=True, status="queued")

    resp = client.get("/api/stats")
    assert resp.status_code == 200
    data = resp.json()
    # FROZEN — 정확히 이 3키만 (SPEC.md §4.2).
    assert set(data.keys()) == {"scans_done", "repos", "last_24h"}
    assert data["scans_done"] == 2
    assert data["repos"] == 2
    assert data["last_24h"] == 1
