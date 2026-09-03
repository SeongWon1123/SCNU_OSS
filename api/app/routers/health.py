"""GET /api/health — SPEC.md §4.2: {ok, db, worker_seen_at}."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.deps import check_db

router = APIRouter()


class HealthResponse(BaseModel):
    ok: bool
    db: bool
    worker_seen_at: datetime | None = None


@router.get("/api/health")
def health() -> HealthResponse:
    # worker_seen_at stays null until the heartbeat table lands in Phase 1.
    return HealthResponse(ok=True, db=check_db(), worker_seen_at=None)
