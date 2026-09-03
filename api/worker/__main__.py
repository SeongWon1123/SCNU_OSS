"""Worker polling loop — claim queued scans, heartbeat every 30s, SIGTERM graceful.

Runnable as `python -m worker` (compose worker command).
"""

import logging
import signal
import time
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal
from app.models import Scan, WorkerHeartbeat
from worker.llm import client as llm_client
from worker.pipeline import run_scan

logger = logging.getLogger(__name__)

_stopping = False


def _handle_sigterm(signum: int, frame: object) -> None:
    global _stopping
    _stopping = True


def recover_interrupted(session: Session) -> None:
    """Startup: scans left 'running' by a restart are marked failed (SPEC §4.3)."""
    with session.begin():
        session.execute(
            update(Scan)
            .where(Scan.status == "running")
            .values(status="failed", error="서버 재시작으로 중단됨 — 다시 시도하세요")
        )


def beat(session: Session) -> None:
    with session.begin():
        row = session.get(WorkerHeartbeat, 1)
        now = datetime.now(UTC)
        if row is None:
            session.add(WorkerHeartbeat(id=1, seen_at=now))
        else:
            row.seen_at = now


def claim_next(session: Session) -> int | None:
    """Short transaction: lock one queued row (skip locked), flip to running, commit."""
    with session.begin():
        scan_id = session.scalar(
            select(Scan.id)
            .where(Scan.status == "queued")
            .order_by(Scan.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if scan_id is None:
            return None
        session.execute(
            update(Scan)
            .where(Scan.id == scan_id)
            .values(status="running", started_at=datetime.now(UTC))
        )
    return scan_id


def _sleep_chunk(seconds: float) -> None:
    for _ in range(int(seconds / 0.1)):
        if _stopping:
            break
        time.sleep(0.1)


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        # §7.1 — worker 기동 시 models.retrieve 1회. 실패해도 기동은 막지 않는다.
        llm_client.startup_probe(Settings())
    except Exception as exc:  # noqa: BLE001 — 프로브 실패는 스캔 시 재확인된다
        logger.warning("LLM 기동 확인 실패(%s) — 스캔 시 재확인", type(exc).__name__)
    with SessionLocal() as session:
        recover_interrupted(session)
        last_beat = 0.0
        while not _stopping:
            now = time.monotonic()
            if now - last_beat >= 30.0:
                beat(session)
                last_beat = now
            scan_id = claim_next(session)
            if scan_id is None:
                _sleep_chunk(2.0)
                continue
            try:
                run_scan(scan_id)
            except Exception as exc:  # noqa: BLE001 — record and keep polling
                session.rollback()
                with session.begin():
                    session.execute(
                        update(Scan)
                        .where(Scan.id == scan_id)
                        .values(status="failed", error=str(exc)[:500])
                    )


if __name__ == "__main__":
    main()
