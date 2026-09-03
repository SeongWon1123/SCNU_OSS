"""GET /api/stats — SPEC.md §4.2 (Phase 7 Should): {scans_done, repos, last_24h}.

정확히 이 3키만 노출한다(FROZEN). owner_token 등 민감값은 응답에 없다.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import deps
from app.models import Scan

router = APIRouter()


class StatsResponse(BaseModel):
    scans_done: int
    repos: int
    last_24h: int


@router.get("/api/stats")
def stats() -> StatsResponse:
    done = Scan.status == "done"
    since = datetime.now(UTC) - timedelta(hours=24)
    with Session(bind=deps.engine) as db:
        scans_done = db.execute(select(func.count()).select_from(Scan).where(done)).scalar_one()
        repos = db.execute(
            select(func.count(func.distinct(func.concat(Scan.owner, "/", Scan.repo)))).where(done)
        ).scalar_one()
        last_24h = db.execute(
            select(func.count()).select_from(Scan).where(done, Scan.finished_at >= since)
        ).scalar_one()
    return StatsResponse(scans_done=scans_done, repos=repos, last_24h=last_24h)
