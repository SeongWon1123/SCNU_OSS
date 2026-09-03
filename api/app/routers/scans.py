"""POST/GET /api/scans — SPEC.md §4.2 (URL normalization, 24h cache, IP rate limit,
token-gated detail, recent 3)."""

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db
from app.deps import get_settings
from app.models import Finding, RateLimitHit, Scan
from app.schemas import RecentScan, ScanCached, ScanCreate, ScanCreated, ScanLimited

router = APIRouter(prefix="/api/scans")

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

_REPO_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/.*)?$")


def normalize_repo_url(raw: str) -> tuple[str, str, str] | None:
    """`https://github.com/{o}/{r}`만 — `.git`·`/tree/x`·슬래시 제거, 아니면 None."""
    cleaned = raw.rstrip("/")
    m = _REPO_RE.match(cleaned)
    if m is None:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"https://github.com/{owner}/{repo}", owner, repo


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _finding_dict(f: Finding) -> dict[str, Any]:
    return {
        "id": f.id,
        "scan_id": f.scan_id,
        "axis": f.axis,
        "scope": f.scope,
        "rule_id": f.rule_id,
        "reg_rule": f.reg_rule,
        "severity": f.severity,
        "confidence": f.confidence,
        "file_path": f.file_path,
        "line_start": f.line_start,
        "line_end": f.line_end,
        "snippet": f.snippet,
        "title_ko": f.title_ko,
        "explain_ko": f.explain_ko,
        "fix_ko": f.fix_ko,
        "weight": f.weight,
    }


def _full_scan_response(db: Session, scan: Scan) -> dict[str, Any]:
    """Token-matched full view. owner_token is NEVER exposed (SPEC: 생성 응답에만 노출)."""
    findings = (
        db.execute(select(Finding).where(Finding.scan_id == scan.id).order_by(Finding.id))
        .scalars()
        .all()
    )
    return {
        "id": scan.id,
        "repo_url": scan.repo_url,
        "owner": scan.owner,
        "repo": scan.repo,
        "consent": scan.consent,
        "commit_sha": scan.commit_sha,
        "default_branch": scan.default_branch,
        "status": scan.status,
        "error": scan.error,
        "score": scan.score,
        "grade": scan.grade,
        "score_detail": scan.score_detail,
        "summary_ko": scan.summary_ko,
        "privacy_policy_md": scan.privacy_policy_md,
        "ai_notice_md": scan.ai_notice_md,
        "meta": scan.meta,
        "created_at": scan.created_at,
        "started_at": scan.started_at,
        "finished_at": scan.finished_at,
        "findings": [_finding_dict(f) for f in findings],
    }


@router.post("", status_code=201)
def create_scan(
    body: ScanCreate,
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> Any:
    normalized = normalize_repo_url(body.repo_url)
    if normalized is None:
        raise HTTPException(status_code=422, detail="공개 GitHub 저장소만 지원합니다")
    canonical_url, owner, repo = normalized

    # 24h cache: same owner+repo done within 24h and no force -> 200 with existing id.
    if not body.force:
        cached = (
            db.execute(
                select(Scan)
                .where(
                    Scan.owner == owner,
                    Scan.repo == repo,
                    Scan.status == "done",
                    Scan.finished_at >= datetime.now(UTC) - timedelta(hours=24),
                )
                .order_by(Scan.finished_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if cached is not None:
            cached_resp = ScanCached(
                id=cached.id,
                status=cached.status,
                queue_position=int(cached.meta.get("queue_position", 0) or 0),
            )
            # 200 (not 201): no new scan, no owner_token, no rate-limit count.
            return JSONResponse(status_code=200, content=jsonable_encoder(cached_resp))

    # Per-IP daily limit on X-Forwarded-For first value (bypass list from settings).
    ip = client_ip(request)
    bypass = {p.strip() for p in settings.rate_limit_bypass_ips.split(",") if p.strip()}
    if ip not in bypass:
        day = datetime.now(UTC).date()
        hit = (
            db.execute(select(RateLimitHit).where(RateLimitHit.ip == ip, RateLimitHit.day == day))
            .scalars()
            .first()
        )
        if hit is not None and hit.hits >= settings.daily_limit_per_ip:
            raise HTTPException(
                status_code=429,
                detail="오늘 스캔 요청 한도에 도달했습니다 — 내일 다시 시도하세요",
            )
        if hit is None:
            db.add(RateLimitHit(ip=ip, day=day, hits=1))
        else:
            hit.hits += 1

    queue_position = (
        db.scalar(select(func.count()).select_from(Scan).where(Scan.status == "queued")) or 0
    )
    scan = Scan(
        repo_url=canonical_url,
        owner=owner,
        repo=repo,
        owner_token=secrets.token_urlsafe(32),
        meta={"explain": body.explain, "queue_position": queue_position},
    )
    db.add(scan)
    db.commit()
    return ScanCreated(
        id=scan.id,
        status=scan.status,
        owner_token=scan.owner_token,
        queue_position=queue_position,
    )


@router.get("/recent", response_model=list[RecentScan])
def recent(db: DbSession) -> list[RecentScan]:
    rows = db.execute(
        select(Scan.owner, Scan.repo, Scan.score, Scan.grade)
        .where(Scan.consent.is_(True), Scan.status == "done")
        .order_by(Scan.finished_at.desc())
        .limit(3)
    ).all()
    return [RecentScan(owner=r.owner, repo=r.repo, score=r.score, grade=r.grade) for r in rows]


@router.get("/{scan_id}")
def get_scan(scan_id: UUID, db: DbSession, t: str = "") -> Any:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="스캔을 찾을 수 없습니다")

    if secrets.compare_digest(scan.owner_token, t or ""):
        return _full_scan_response(db, scan)

    limited = ScanLimited(
        id=scan.id,
        status=scan.status,
        score=scan.score,
        grade=scan.grade,
        score_detail=scan.score_detail,
        progress=scan.meta.get("progress"),
        message="상세는 스캔 생성자만 볼 수 있습니다",
    )
    if scan.status == "running":
        partial = db.execute(select(Finding).where(Finding.scan_id == scan.id)).scalars().all()
        if partial:
            resp = limited.model_dump()
            resp["findings"] = [_finding_dict(f) for f in partial]
            return resp
    return limited.model_dump()


def _markdown_document(scan: Scan, column: str) -> Response:
    """SPEC:146-147 — token-gated text/markdown; 문서가 없으면 404."""
    document = getattr(scan, column)
    if document is None:
        raise HTTPException(status_code=404, detail="문서가 아직 생성되지 않았습니다")
    return Response(content=document, media_type="text/markdown; charset=utf-8")


@router.get("/{scan_id}/privacy-policy.md")
def get_privacy_policy_md(scan_id: UUID, db: DbSession, t: str = "") -> Response:
    scan = db.get(Scan, scan_id)
    if scan is None or not secrets.compare_digest(scan.owner_token, t or ""):
        raise HTTPException(status_code=404, detail="스캔을 찾을 수 없습니다")
    return _markdown_document(scan, "privacy_policy_md")


@router.get("/{scan_id}/ai-notice.md")
def get_ai_notice_md(scan_id: UUID, db: DbSession, t: str = "") -> Response:
    """R6 산출물만 존재(SPEC:147) — AI 고지가 없는 스캔은 404."""
    scan = db.get(Scan, scan_id)
    if scan is None or not secrets.compare_digest(scan.owner_token, t or ""):
        raise HTTPException(status_code=404, detail="스캔을 찾을 수 없습니다")
    return _markdown_document(scan, "ai_notice_md")
