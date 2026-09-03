"""GET /api/badge/{owner}/{repo}.svg — SPEC.md §4.2 (Phase 7 Should).

consent=true 상태의 최근 done 스캔 점수를 shields.io 스타일 SVG로 자체 렌더링한다
(외부 요청 금지). 좌 라벨은 PROMPTS.md:144 동결 지정 "리포닥" — 영문명 확정(D2) 시
BADGE_LABEL 상수만 교체한다. 없으면 회색 "not scanned". Cache-Control max-age=300.
"""

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import deps
from app.models import Scan

router = APIRouter()

# PROMPTS.md:144 동결 라벨 — D2에서 영문명 확정 시 이 상수만 교체.
BADGE_LABEL = "리포닥"
NOT_SCANNED_TEXT = "not scanned"

# 등급색 매핑 — SPEC에 동결값이 없어 shields.io 관례색을 문서화해 사용:
# A=초록, B=파랑, C=노랑, D=주황, F=빨강.
GRADE_COLORS: dict[str, str] = {
    "A": "#97ca00",
    "B": "#007ec6",
    "C": "#dfb317",
    "D": "#fe7d37",
    "F": "#e05d44",
}
LABEL_COLOR = "#555"
NOT_SCANNED_COLOR = "#9f9f9f"
VALUE_COLOR_FALLBACK = "#9f9f9f"

_SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{aria}">
<title>{aria}</title>
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<clipPath id="r"><rect width="{width}" height="20" rx="3" fill="#fff"/></clipPath>
<g clip-path="url(#r)">
<rect width="{left_w}" height="20" fill="{left_color}"/>
<rect x="{left_w}" width="{right_w}" height="20" fill="{right_color}"/>
<rect width="{width}" height="20" fill="url(#s)"/>
</g>
<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="110" transform="scale(.1)">
<text x="{lx}" y="150" fill="#010101" fill-opacity=".3" textLength="{lt}">{left}</text>
<text x="{lx}" y="140" textLength="{lt}">{left}</text>
<text x="{rx}" y="150" fill="#010101" fill-opacity=".3" textLength="{rt}">{right}</text>
<text x="{rx}" y="140" textLength="{rt}">{right}</text>
</g>
</svg>"""


def _text_px(text: str) -> int:
    # CJK 글자 ≈ 11px, 나머지 ≈ 6.5px + 양쪽 패딩 10px (shields.io 근사).
    width = sum(11.0 if ord(ch) > 0x2E7F else 6.5 for ch in text)
    return int(width) + 10


def _render_badge(left: str, right: str, left_color: str, right_color: str) -> str:
    left_w = _text_px(left)
    right_w = _text_px(right)
    return _SVG_TEMPLATE.format(
        width=left_w + right_w,
        aria=f"{left}: {right}",
        left_w=left_w,
        right_w=right_w,
        left_color=left_color,
        right_color=right_color,
        lx=left_w * 5,
        rx=(left_w + right_w // 2) * 5,
        lt=(left_w - 10) * 10,
        rt=(right_w - 10) * 10,
        left=left,
        right=right,
    )


@router.get("/api/badge/{owner}/{repo}.svg")
def badge(owner: str, repo: str) -> Response:
    with Session(bind=deps.engine) as db:
        scan = db.execute(
            select(Scan.score, Scan.grade)
            .where(
                Scan.owner == owner,
                Scan.repo == repo,
                Scan.consent.is_(True),
                Scan.status == "done",
            )
            .order_by(Scan.finished_at.desc())
            .limit(1)
        ).first()

    if scan is None or scan.score is None or scan.grade is None:
        svg = _render_badge(BADGE_LABEL, NOT_SCANNED_TEXT, LABEL_COLOR, NOT_SCANNED_COLOR)
    else:
        grade = str(scan.grade).strip()
        svg = _render_badge(
            BADGE_LABEL,
            f"{scan.score} · {grade}",
            LABEL_COLOR,
            GRADE_COLORS.get(grade, VALUE_COLOR_FALLBACK),
        )
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "max-age=300"},
    )
