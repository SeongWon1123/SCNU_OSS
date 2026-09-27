"""SPEC §4.3 총 300초 가드 — _run_scan_guarded 래퍼. DB 사용(실 Postgres)."""

import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import deps
from app.models import Scan
from worker import __main__ as worker_main


def _insert_queued(owner: str, repo: str) -> str:
    scan = Scan(
        repo_url=f"https://github.com/{owner}/{repo}",
        owner=owner,
        repo=repo,
        owner_token="tok-" + uuid.uuid4().hex,
        consent=False,
        status="queued",
        meta={},
        created_at=datetime.now(UTC),
    )
    with Session(bind=deps.engine) as session:
        session.add(scan)
        session.commit()
        return str(scan.id)


def _status(scan_id: str) -> tuple[str, str | None]:
    with Session(bind=deps.engine) as session:
        row = session.get(Scan, uuid.UUID(scan_id))
        return row.status, row.error


def test_guarded_marks_timeout_scan_failed_without_waiting_full_budget():
    scan_id = _insert_queued(f"t-{uuid.uuid4().hex[:8]}", "repo")

    def _slow(_sid: object) -> None:
        time.sleep(5)

    started = time.monotonic()
    with Session(bind=deps.engine) as session:
        worker_main._run_scan_guarded(session, uuid.UUID(scan_id), run_fn=_slow, timeout=0.2)
    elapsed = time.monotonic() - started

    status, error = _status(scan_id)
    assert status == "failed"
    assert error == "전체 시간 초과"
    assert elapsed < 4, f"guard did not cut the call: {elapsed:.1f}s"


def test_guarded_passes_through_fast_scan_result():
    scan_id = _insert_queued(f"t-{uuid.uuid4().hex[:8]}", "repo")
    seen: list[object] = []

    def _fast(sid: object) -> None:
        seen.append(sid)

    with Session(bind=deps.engine) as session:
        worker_main._run_scan_guarded(session, uuid.UUID(scan_id), run_fn=_fast, timeout=10)

    assert seen == [uuid.UUID(scan_id)]
    status, _ = _status(scan_id)
    assert status == "queued"  # 래퍼는 성공 시 상태를 바꾸지 않는다(파이프라인이 정한다)
