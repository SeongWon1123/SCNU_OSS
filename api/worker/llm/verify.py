"""검증 — SPEC.md §7.3 순수 함수. DB·I/O 없음.

1. citations.finding_id가 요청에 보낸 id 집합에 있어야 한다 — 하나도 없으면 항목
   폐기(rule_id 자체가 보내지 않은 것 → 불일치 폐기 포함, 같은 카운터).
2. 수치 필터: 문장에 (벌금|과태료|징역|금고|처벌)이 있거나 금액·기간 정규식이
   매치하면 그 문장을 삭제한다.

수치 정규식은 SPEC.md:256 동결 문자열이다. 다만 첫 대안의 (만|억)?를 (만|억)으로
읽는다 — 동결 테스트("100원 테스트 결제"·"제3원칙" 통과, "3천만원" 삭제)와 함께
읽으면 만/억 단위 필수가 유일한 일관 해석이고, 선택적 `?` 그대로는 "100원"·"3원"을
매치시켜 통과 케이스 둘을 깬다. 차이는 `?` 한 글자이며 PR계약 ⑥에 기록한다.
"""

import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
PENALTY_KEYWORD_RE = re.compile(r"(벌금|과태료|징역|금고|처벌)")
NUMBER_RE = re.compile(
    r"(\d[\d,.]*\s*(천|백|십)?(만|억)\s*원"  # 아랍 숫자 + 만/억 단위 필수 + 원
    r"|[일이삼사오육칠팔구십백천만억]{1,6}\s*원"  # 한국 숫자 + 원
    r"|\d+\s*개?(월|년)\s*(이하|이상))"  # 기간 + 이하/이상
)


def split_sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]


def strip_numbers(text: str) -> tuple[str, int]:
    """§7.3-2 — 금액·형량 키워드/정규식이 걸린 문장 삭제. 반환 (정제문, 삭제 수).

    삭제가 없으면 원문을 그대로 되돌린다(포맷 보존). 삭제 문장이 있는 경우 남은
    문장을 공백으로 이어 붙인다.
    """
    if not text:
        return text, 0
    kept: list[str] = []
    dropped = 0
    for sentence in split_sentences(text):
        if PENALTY_KEYWORD_RE.search(sentence) or NUMBER_RE.search(sentence):
            dropped += 1
            continue
        kept.append(sentence.strip())
    if dropped == 0:
        return text, 0
    return " ".join(kept), dropped


def validate_citations(
    items: list[dict],
    sent_ids_by_rule: dict[str, set[int]],
) -> tuple[list[dict], int]:
    """§7.3-1 — rule_id·citations를 보낸 집합과 대조.

    항목의 citations 중 보낸 id가 하나라도 있으면 통과(유효한 인용만 남김),
    하나도 없으면 폐기한다(rule_id 불일치 포함). 반환 (유효 항목, 폐기 수).
    """
    valid: list[dict] = []
    dropped = 0
    for item in items:
        allowed = sent_ids_by_rule.get(str(item.get("rule_id", "")), set())
        cited = {
            c.get("finding_id")
            for c in (item.get("citations") or [])
            if isinstance(c, dict) and isinstance(c.get("finding_id"), int)
        }
        overlap = allowed & cited
        if not overlap:
            dropped += 1
            continue
        valid.append({**item, "citations": [{"finding_id": fid} for fid in sorted(overlap)]})
    return valid, dropped
