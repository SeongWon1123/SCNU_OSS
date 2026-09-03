"""요약 — SPEC.md §7.5: 3문장(점수·최상위 규제 의무·시크릿 건수).

findings 0건이면 LLM 호출 없이 고정 문구. LLM 요약에도 §7.3-2 수치 필터만
적용한다(인용 검증 대상 아님).
"""

import json
import logging
from typing import Any

from worker import catalog as catalog_mod
from worker.llm import client as llm_client
from worker.llm import verify

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = (
    "스캔 결과를 한국어 존뱃말로 정확히 3문장으로 요약하세요. "
    "순서는 진단 점수, 최상위 규제 의무, 시크릿 건수입니다. "
    "법령의 금액·형량·기간 수치는 절대 쓰지 마세요."
)

SUMMARY_SCHEMA: dict = {
    "type": "object",
    "properties": {"summary_ko": {"type": "string"}},
    "required": ["summary_ko"],
    "additionalProperties": False,
}

MAX_OUTPUT_TOKENS = 400


def _top_duty(findings: list[dict[str, Any]]) -> str:
    """규제 기여(가중치 합)가 가장 큰 reg_rule의 카탈로그 의무명."""
    per_rule: dict[str, int] = {}
    for finding in findings:
        rule = finding.get("reg_rule")
        if finding.get("axis") == "regulation" and rule:
            per_rule[str(rule)] = per_rule.get(str(rule), 0) + int(finding.get("weight") or 0)
    if not per_rule:
        return ""
    top = max(sorted(per_rule), key=lambda rule: per_rule[rule])
    block = catalog_mod.load().get(top) or {}
    return str(block.get("name", ""))


def fallback_text(findings: list[dict[str, Any]], score: int | None, grade: str | None) -> str:
    """LLM 없이 만드는 고정 3문장. findings 0건 케이스를 포함한다."""
    if not findings:
        return (
            f"발견된 보안·규제 항목이 없습니다. 진단 점수는 {score or 0}점"
            f"({grade or '-'}등급)입니다. 노출된 시크릿도 없습니다."
        )
    secret_count = sum(1 for f in findings if f.get("axis") == "secrets")
    duty = _top_duty(findings)
    sentences = [f"진단 점수는 {score or 0}점({grade or '-'}등급)입니다."]
    sentences.append(
        f"가장 먼저 확인할 항목은 {duty}입니다." if duty else "확인할 규제 항목이 있습니다."
    )
    sentences.append(
        f"하드닝이 필요한 시크릿은 {secret_count}건입니다."
        if secret_count
        else "노출된 시크릿은 없습니다."
    )
    return " ".join(sentences)


def run(
    findings: list[dict[str, Any]],
    score: int | None,
    grade: str | None,
    llm: llm_client.LLMClient,
    budget: llm_client.Budget,
) -> tuple[str | None, int]:
    """LLM 요약 시도. findings 0건·실패·예산 초과 시 (None, 0) — 호출자가 고정 문구 사용."""
    if not findings or not llm.probe():
        return None, 0
    try:
        payload = {
            "score": score,
            "grade": grade,
            "top_duty": _top_duty(findings),
            "secret_count": sum(1 for f in findings if f.get("axis") == "secrets"),
        }
        data = llm.chat_json(
            budget,
            SUMMARY_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
            "scan_summary",
            SUMMARY_SCHEMA,
            MAX_OUTPUT_TOKENS,
        )
        if not isinstance(data, dict) or not data.get("summary_ko"):
            return None, 0
        return verify.strip_numbers(str(data["summary_ko"]))
    except Exception:
        logger.exception("요약 LLM 실패 — 고정 문구로 대체(절대규칙 5)")
        return None, 0
