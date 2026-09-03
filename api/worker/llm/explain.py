"""해설 — SPEC.md §7.2: rule_id 그룹 ≤12(severity·weight 순), 그룹당 대표 ≤5,
json_schema strict, 그룹의 모든 finding에 같은 explain_ko/fix_ko.

시스템 프롬프트는 SPEC.md:251 고정 문구를 그대로 상수로 둔다(수정 금지).
"""

import json
import logging
from typing import Any

from sqlalchemy import select, update

from app.config import Settings
from app.db import SessionLocal
from app.models import Finding, Scan
from worker import catalog as catalog_mod
from worker.llm import client as llm_client
from worker.llm import verify

logger = logging.getLogger(__name__)

# SPEC.md:251 고정 문구 — verbatim, 수정 금지.
SYSTEM_PROMPT = (
    "제공된 findings 외 사실을 만들지 마라. 모든 문장은 citations의 finding에 근거한다. "
    "법령의 금액·형량·기간 수치는 절대 쓰지 말고 law_ref 이름만 언급하라. "
    "코드가 하는 일을 단정하지 말고 '~로 보입니다'로, 서버 전송·저장 여부는 스니펫에 "
    "보일 때만 언급하라. 한국어 존댓말, 비전공자 대상."
)

MAX_GROUPS = 12
MAX_REPRESENTATIVES = 5
SNIPPET_CHARS = 300
MAX_OUTPUT_TOKENS = 4000

SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "error": 1,
    "warning": 2,
    "medium": 2,
    "info": 3,
    "low": 4,
}

EXPLAIN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "title_ko": {"type": "string"},
                    "why_ko": {"type": "string"},
                    "fix_ko": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"finding_id": {"type": "integer"}},
                            "required": ["finding_id"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["rule_id", "title_ko", "why_ko", "fix_ko", "citations"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def _sev_rank(severity: str) -> int:
    return SEVERITY_RANK.get(str(severity).lower(), 3)


def _law_refs() -> dict[str, str]:
    """reg_rule(R1..R7) → 카탈로그 law(조문 이름만 — 수치 금지)."""
    catalog = catalog_mod.load()
    return {
        rule: str(block.get("law", ""))
        for rule, block in catalog.items()
        if isinstance(block, dict)
    }


def group_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """rule_id 그룹 — severity·weight 순, 그룹 ≤12, 대표 ≤5. 순수 함수."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        grouped.setdefault(str(finding["rule_id"]), []).append(finding)
    ranked = sorted(
        grouped.values(),
        key=lambda members: (
            min(_sev_rank(str(m["severity"])) for m in members),
            -max(int(m["weight"]) for m in members),
        ),
    )[:MAX_GROUPS]
    groups: list[dict[str, Any]] = []
    for members in ranked:
        ordered = sorted(members, key=lambda m: (_sev_rank(str(m["severity"])), -int(m["weight"])))
        groups.append(
            {
                "rule_id": str(ordered[0]["rule_id"]),
                "reg_rule": str(ordered[0].get("reg_rule") or ""),
                "member_ids": [int(m["finding_id"]) for m in ordered],
                "representatives": ordered[:MAX_REPRESENTATIVES],
            }
        )
    return groups


def build_payload(
    groups: list[dict[str, Any]], law_refs: dict[str, str]
) -> tuple[dict[str, Any], dict[str, set[int]], dict[str, list[int]]]:
    """LLM 요청 JSON과 (보낸 대표 id / 그룹 전체 id) 지도를 만든다."""
    payload_groups: list[dict[str, Any]] = []
    sent_ids_by_rule: dict[str, set[int]] = {}
    member_ids_by_rule: dict[str, list[int]] = {}
    for group in groups:
        rule_id = group["rule_id"]
        law_ref = law_refs.get(group["reg_rule"], "")
        representatives = [
            {
                "finding_id": int(f["finding_id"]),
                "file": str(f.get("file_path") or ""),
                "line": f.get("line_start"),
                "snippet": str(f.get("snippet") or "")[:SNIPPET_CHARS],
                "law_ref": law_ref,
            }
            for f in group["representatives"]
        ]
        payload_groups.append({"rule_id": rule_id, "law_ref": law_ref, "findings": representatives})
        sent_ids_by_rule[rule_id] = {int(f["finding_id"]) for f in group["representatives"]}
        member_ids_by_rule[rule_id] = group["member_ids"]
    return {"groups": payload_groups}, sent_ids_by_rule, member_ids_by_rule


def _fresh_meta(settings: Settings) -> dict[str, Any]:
    return {
        "model": settings.openai_model,
        "calls": 0,
        "status": "skipped",
        "explained": 0,
        "dropped_by_citation": 0,
        "dropped_by_number": 0,
    }


def run(scan_id: str, settings: Settings) -> dict[str, Any]:
    """explain 단계 — meta.llm 값을 만들고 findings에 해설을 적용한다.

    어떤 실패도 스캔을 실패시키지 않는다(절대규칙 5): 예외는 삼키고
    status='skipped' meta를 돌려준다.
    """
    meta = _fresh_meta(settings)
    try:
        with SessionLocal() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                return meta
            if not (scan.meta or {}).get("explain", True):
                meta["status"] = "explain_off"
                return meta
            rows = session.scalars(select(Finding).where(Finding.scan_id == scan.id)).all()
            findings = [_row_dict(row) for row in rows]
        if not findings:
            meta["status"] = "ok"  # 해설할 항목 없음 — LLM 호출 없음
            return meta

        llm = llm_client.LLMClient(settings)
        if not llm.probe():
            return meta  # skipped — 키/모델 미설정 또는 모델 확인 실패
        budget = llm_client.budget_for(str(scan_id))
        payload, sent_ids_by_rule, member_ids_by_rule = build_payload(
            group_findings(findings), _law_refs()
        )
        data = llm.chat_json(
            budget,
            SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=False),
            "explain_output",
            EXPLAIN_SCHEMA,
            MAX_OUTPUT_TOKENS,
        )
        meta["calls"] = budget.calls
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return meta  # skipped — 429·파싱 실패·예산 초과

        valid, dropped_citations = verify.validate_citations(items, sent_ids_by_rule)
        meta["dropped_by_citation"] = dropped_citations
        explained = 0
        dropped_numbers = 0
        with SessionLocal() as session:
            for item in valid:
                why, why_dropped = verify.strip_numbers(str(item.get("why_ko") or ""))
                fix, fix_dropped = verify.strip_numbers(str(item.get("fix_ko") or ""))
                dropped_numbers += why_dropped + fix_dropped
                ids = member_ids_by_rule.get(str(item.get("rule_id", "")), [])
                if not ids or not why or not fix:
                    continue
                result = session.execute(
                    update(Finding).where(Finding.id.in_(ids)).values(explain_ko=why, fix_ko=fix)
                )
                explained += result.rowcount or 0
            session.commit()
        meta["explained"] = explained
        meta["dropped_by_number"] = dropped_numbers
        meta["status"] = "ok"
        return meta
    except Exception:
        logger.exception("explain 단계 실패 — 스캔은 계속됩니다(절대규칙 5)")
        return meta


def _row_dict(row: Finding) -> dict[str, Any]:
    return {
        "finding_id": int(row.id),
        "rule_id": row.rule_id,
        "reg_rule": row.reg_rule,
        "axis": row.axis,
        "severity": row.severity,
        "weight": row.weight,
        "file_path": row.file_path,
        "line_start": row.line_start,
        "snippet": row.snippet,
    }
