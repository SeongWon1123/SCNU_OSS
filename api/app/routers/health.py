"""GET /api/health — SPEC.md §4.2: {ok, db, worker_seen_at}."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import deps
from app.deps import check_db
from app.models import WorkerHeartbeat

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool
    db: bool
    worker_seen_at: datetime | None = None


@router.get("/api/health")
def health() -> HealthResponse:
    # Named failure boundary: the heartbeat table may be unmigrated (or the test
    # engine may lack it) — a missing table must not fail the health probe.
    worker_seen_at = None
    try:
        with Session(bind=deps.engine) as session:
            row = session.get(WorkerHeartbeat, 1)
            if row is not None:
                worker_seen_at = row.seen_at
    except SQLAlchemyError:
        worker_seen_at = None
    return HealthResponse(ok=True, db=check_db(), worker_seen_at=worker_seen_at)
