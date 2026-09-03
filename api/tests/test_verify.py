"""§7.3 검증 순수 함수 — 동결 케이스(삭제 5·통과 3) + 인용/불일치 폐기. DB 없음."""

from worker.llm import verify
from worker.llm.explain import MAX_GROUPS, MAX_REPRESENTATIVES, group_findings

DELETED_SENTENCES = (
    "이용자 정보 유출 시 3천만원 상당의 제재가 있습니다.",
    "계약 위반에는 1,000만원 이하의 제재가 따릅니다.",
    "규모가 큰 침해는 천만원 이상의 문제가 될 수 있습니다.",
    "자격 정지는 6개월 이하의 기간으로 제한됩니다.",
    "위반 시 과태료가 부과될 수 있습니다.",
)
KEPT_SENTENCES = (
    "결제 연동은 100원 테스트 결제로 확인했습니다.",
    "개인정보 처리 제3원칙을 준수합니다.",
    "무료 체험 기간은 1개월입니다.",
)


def test_number_filter_drops_frozen_amount_sentences():
    for sentence in DELETED_SENTENCES:
        cleaned, dropped = verify.strip_numbers(sentence)
        assert dropped == 1, sentence
        assert sentence not in cleaned


def test_number_filter_keeps_frozen_small_amount_sentences():
    for sentence in KEPT_SENTENCES:
        cleaned, dropped = verify.strip_numbers(sentence)
        assert dropped == 0, sentence
        assert sentence in cleaned


def test_number_filter_mixed_text_drops_only_flagged_sentence():
    text = f"{KEPT_SENTENCES[0]} {DELETED_SENTENCES[4]} {KEPT_SENTENCES[2]}"

    cleaned, dropped = verify.strip_numbers(text)

    assert dropped == 1
    assert "과태료" not in cleaned
    assert KEPT_SENTENCES[0] in cleaned and KEPT_SENTENCES[2] in cleaned


def test_number_filter_is_noop_without_flags():
    text = "서버는 이메일을 저장하지 않는 것으로 보입니다. 코드가 하는 일을 단정할 수 없습니다."

    cleaned, dropped = verify.strip_numbers(text)

    assert dropped == 0
    assert cleaned == text


def test_citation_item_dropped_when_no_sent_ids_match():
    items = [{"rule_id": "R1", "citations": [{"finding_id": 999}]}]

    valid, dropped = verify.validate_citations(items, {"R1": {1, 2}})

    assert valid == [] and dropped == 1


def test_mismatched_rule_id_item_dropped():
    items = [{"rule_id": "R9", "citations": [{"finding_id": 1}]}]

    valid, dropped = verify.validate_citations(items, {"R1": {1}})

    assert valid == [] and dropped == 1


def test_valid_citations_kept_and_filtered_to_sent_ids():
    items = [
        {
            "rule_id": "R1",
            "title_ko": "t",
            "why_ko": "w",
            "fix_ko": "f",
            "citations": [{"finding_id": 1}, {"finding_id": 404}],
        }
    ]

    valid, dropped = verify.validate_citations(items, {"R1": {1, 2}})

    assert dropped == 0
    assert valid[0]["citations"] == [{"finding_id": 1}]


def _finding(rule_id: str, severity: str, weight: int, finding_id: int) -> dict:
    return {
        "finding_id": finding_id,
        "rule_id": rule_id,
        "reg_rule": rule_id,
        "axis": "regulation",
        "severity": severity,
        "weight": weight,
        "file_path": "a.py",
        "line_start": 1,
        "snippet": "x",
    }


def test_group_findings_caps_and_severity_weight_order():
    findings = [_finding("R1", "warning", 8, i) for i in range(1, 21)]
    findings.append(_finding("R7", "critical", 20, 99))

    groups = group_findings(findings)

    assert len(groups) <= MAX_GROUPS
    assert groups[0]["rule_id"] == "R7"
    assert len(groups[0]["representatives"]) <= MAX_REPRESENTATIVES
    assert len(groups[0]["member_ids"]) == 1
    assert len([g for g in groups if g["rule_id"] == "R1"]) == 1
    r1 = next(g for g in groups if g["rule_id"] == "R1")
    assert len(r1["member_ids"]) == 20
    assert len(r1["representatives"]) == MAX_REPRESENTATIVES
