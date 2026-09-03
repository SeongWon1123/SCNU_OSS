"""개인정보처리방침·AI 고지 초안 — SPEC.md §7.4.

신호→고정 문구(처리 목적 매핑 동결). LLM은 "서비스 설명" 1필드만 — README 첫
300자를 입력으로 받고, README가 없거나 300자 미만이면 호출하지 않고
"[서비스 설명을 입력하세요]"로 채운다. 프롬프트에 "README에 없는 기능을 추측하지
말 것"을 포함한다(§7.4:263).
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select

from app.config import Settings
from app.db import SessionLocal
from app.models import Finding, Scan
from worker.llm import client as llm_client
from worker.llm import summary as summary_mod
from worker.llm import verify

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# SPEC.md:262 신호→고정 문구 (동결).
PURPOSE_BY_RULE = {
    "R1": "위치 기반 서비스 제공",
    "R2": "회원 식별·연락",
    "R3": "결제·배송",
    "R5": "마케팅 정보 전송(동의 시)",
    "R6": "AI 응답 생성",
}
_PURPOSE_ORDER = ("R2", "R3", "R1", "R5", "R6")

# SPEC.md:261 R2 필드→한국어 (위치정보는 R1 지오 스니펫의 latitude/longitude에서).
ITEM_LABELS = (
    ("email", "이메일"),
    ("phone", "전화번호"),
    ("name", "이름"),
    ("birth", "생년월일"),
    ("address", "주소"),
    ("geo", "위치정보"),
)
_ITEM_TOKEN_RE = r"\b(e_?mail|phone(?:_number|_no)?|latitude|longitude|birth(?:date|day)?|(?:full|real)_name|address)\b"

SERVICE_SYSTEM = (
    "아래 README 발췌만 근거로 서비스 설명 1~2문장을 한국어 존댓말로 작성하세요. "
    "README에 없는 기능을 추측하지 말 것."
)
SERVICE_SCHEMA: dict = {
    "type": "object",
    "properties": {"service_description_ko": {"type": "string"}},
    "required": ["service_description_ko"],
    "additionalProperties": False,
}
SERVICE_MAX_OUTPUT_TOKENS = 400
README_INPUT_CHARS = 300
NO_SERVICE_DESCRIPTION = "[서비스 설명을 입력하세요]"

# SPEC.md:264 상단 고정 고지문 — verbatim.
FIXED_NOTICE = (
    "본 초안은 코드 분석 결과를 기반으로 자동 생성된 참고용 문서이며 법률 자문이 아닙니다. "
    "[ ] 항목을 채우고 개인정보보호위원회 작성지침으로 최종 확인하세요."
)


def _item_codes(snippet: str | None) -> set[str]:
    if not snippet:
        return set()
    codes: set[str] = set()
    for match in re.finditer(_ITEM_TOKEN_RE, snippet, re.IGNORECASE):
        token = match.group(0).lower()
        if token.startswith(("email", "e_mail")):
            codes.add("email")
        elif token.startswith("phone"):
            codes.add("phone")
        elif token in ("latitude", "longitude"):
            codes.add("geo")
        elif token.startswith("birth"):
            codes.add("birth")
        elif token.endswith("name"):
            codes.add("name")
        else:
            codes.add("address")
    return codes


def collect_signals(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """§7.4 코드 변수 — 순수 함수. regulation 스니펫에서 수집 항목·신호를 뽑는다."""
    regulation = [f for f in findings if f.get("axis") == "regulation"]
    rules = {str(f["reg_rule"]) for f in regulation if f.get("reg_rule")}
    found_codes: set[str] = set()
    for finding in regulation:
        found_codes |= _item_codes(finding.get("snippet"))
    third_parties: list[str] = []
    if "R3" in rules:
        third_parties.append("결제 서비스 제공사")
    if "R1" in rules:
        third_parties.append("지도·위치 기능 제공사")
    if "R6" in rules:
        third_parties.append("생성형 AI 서비스 공급사")
    return {
        "collected_items": [label for code, label in ITEM_LABELS if code in found_codes],
        "uses_location": "R1" in rules,
        "uses_analytics": any(
            str(f.get("rule_id", "")).endswith("kr-r2-analytics-sdk") for f in regulation
        ),
        "uses_ai": "R6" in rules,
        "third_parties": third_parties,
        "purposes": [PURPOSE_BY_RULE[r] for r in _PURPOSE_ORDER if r in rules],
    }


def readme_service_input(checkout_dir: str) -> str | None:
    """README 첫 300자. README가 없거나 300자 미만이면 None(§7.4 — 호출 금지)."""
    directory = Path(checkout_dir)
    if not directory.is_dir():
        return None
    for candidate in sorted(directory.glob("README*")):
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if len(text) < README_INPUT_CHARS:
            return None
        return text[:README_INPUT_CHARS]
    return None


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR), keep_trailing_newline=True, autoescape=False
    )


def render_policy(context: dict[str, Any], service_description: str, repo_label: str) -> str:
    return (
        _env()
        .get_template("privacy_policy.md.j2")
        .render(
            **context,
            service_description=service_description,
            notice=FIXED_NOTICE,
            repo_label=repo_label,
        )
    )


def render_ai_notice() -> str:
    return _env().get_template("ai_notice.md.j2").render(notice=FIXED_NOTICE)


def run(scan_id: str, checkout_dir: str, settings: Settings) -> None:
    """policy 단계 — 방침·AI 고지·요약을 만들어 스캔 행에 저장(자체 트랜잭션).

    LLM 실패는 스캔 실패가 아니다(절대규칙 5): 서비스 설명·요약은 고정 문구로
    폴백하고 렌더링은 항상 완료된다.
    """
    try:
        with SessionLocal() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                return
            rows = session.scalars(select(Finding).where(Finding.scan_id == scan.id)).all()
            findings = [_row_dict(row) for row in rows]
            meta = dict(scan.meta or {})
            llm_meta = dict(meta.get("llm") or {})
            service_description = NO_SERVICE_DESCRIPTION
            summary_text: str | None = None
            if meta.get("explain", True):
                llm = llm_client.LLMClient(settings)
                budget = llm_client.budget_for(str(scan_id))
                calls_before = budget.calls
                if llm.probe():
                    readme = readme_service_input(checkout_dir)
                    if readme is not None:
                        data = llm.chat_json(
                            budget,
                            SERVICE_SYSTEM,
                            json.dumps({"readme": readme}, ensure_ascii=False),
                            "service_description",
                            SERVICE_SCHEMA,
                            SERVICE_MAX_OUTPUT_TOKENS,
                        )
                        if isinstance(data, dict) and data.get("service_description_ko"):
                            description, dropped = verify.strip_numbers(
                                str(data["service_description_ko"])
                            )
                            if description:
                                service_description = description
                            llm_meta["dropped_by_number"] = (
                                llm_meta.get("dropped_by_number", 0) + dropped
                            )
                    summary_text, dropped = summary_mod.run(
                        findings, scan.score, scan.grade, llm, budget
                    )
                    llm_meta["dropped_by_number"] = llm_meta.get("dropped_by_number", 0) + dropped
                llm_meta["calls"] = llm_meta.get("calls", 0) + (budget.calls - calls_before)
            if summary_text is None:
                summary_text = summary_mod.fallback_text(findings, scan.score, scan.grade)
            signals = collect_signals(findings)
            scan.privacy_policy_md = render_policy(
                signals, service_description, f"{scan.owner}/{scan.repo}"
            )
            if signals["uses_ai"]:
                scan.ai_notice_md = render_ai_notice()
            scan.summary_ko = summary_text
            meta["llm"] = llm_meta
            scan.meta = meta
            session.commit()
    except Exception:
        logger.exception("policy 단계 실패 — 스캔은 계속됩니다(절대규칙 5)")


def _row_dict(row: Finding) -> dict[str, Any]:
    return {
        "axis": row.axis,
        "rule_id": row.rule_id,
        "reg_rule": row.reg_rule,
        "snippet": row.snippet,
        "weight": row.weight,
    }
