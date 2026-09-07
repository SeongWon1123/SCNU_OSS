"""SPEC §7.5 요약 회귀 — 시크릿 건수는 gitleaks rule_id 기준. DB 없음."""

from worker.llm import summary


def _gitleaks_finding() -> dict:
    return {
        "axis": "security",
        "rule_id": "gitleaks:openai-api-key",
        "reg_rule": None,
        "weight": 15,
    }


def test_fallback_counts_gitleaks_findings_as_secrets():
    findings = [_gitleaks_finding(), _gitleaks_finding()]

    text = summary.fallback_text(findings, 70, "C")

    assert "2건" in text
    assert "노출된 시크릿은 없습니다" not in text


def test_fallback_zero_when_no_gitleaks_findings():
    findings = [{"axis": "regulation", "rule_id": "semgrep:kr-r1", "reg_rule": "R1", "weight": 8}]

    text = summary.fallback_text(findings, 90, "A")

    assert "노출된 시크릿은 없습니다" in text
