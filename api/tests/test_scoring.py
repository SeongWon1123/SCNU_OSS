"""SPEC §6:224-237 — the 6 frozen scoring cases + R1/R2 confidence rules.

Pure-function tests: no DB, no I/O. The catalog is the real frozen
rules/catalog.yaml (weight_caps R1 15, R2 15, R3 12, R5 6, R6 12, R7 20).
"""

from typing import Any

from worker import catalog as catalog_mod
from worker.scanners import gitleaks
from worker.scoring import apply_confidence_rules, compute

CATALOG: dict[str, Any] = catalog_mod.load()


def _finding(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "axis": "security",
        "scope": "app",
        "rule_id": "gitleaks:aws-key",
        "reg_rule": None,
        "severity": "critical",
        "confidence": None,
        "file_path": "a.js",
        "snippet": "sk****",
        "weight": 15,
    }
    base.update(overrides)
    return base


def _reg(rule: str, rule_id: str, weight: int, **overrides: Any) -> dict[str, Any]:
    return _finding(
        axis="regulation",
        rule_id=rule_id,
        reg_rule=rule,
        severity="medium",
        confidence="medium",
        weight=weight,
        **overrides,
    )


def test_case1_zero_findings_score_100_grade_a():
    result = compute([], CATALOG)

    assert result == {
        "score": 100,
        "grade": "A",
        "detail": {"security": 40, "regulation": 40, "license": 20},
    }


def test_case2_three_secrets_security_budget_exhausted():
    # 시크릿 3건 → security 0: 3×15=45 → capped at 40 → detail.security == 0.
    findings = [_finding(rule_id=f"gitleaks:key{i}") for i in range(3)]

    result = compute(findings, CATALOG)

    assert 40 - result["detail"]["security"] == 40  # security_penalty == 40
    assert result["detail"]["security"] == 0
    assert result["score"] == 60
    assert result["grade"] == "C"


def test_case3_twenty_r1_findings_regulation_capped_at_15():
    # 20 × weight 8 = 160 → min(R1 weight_cap 15, 160) = 15 → rp ≤ 15.
    findings = [_reg("R1", "semgrep:kr-r1-browser-geolocation", 8) for _ in range(20)]

    result = compute(findings, CATALOG)

    regulation_penalty = 40 - result["detail"]["regulation"]
    assert regulation_penalty == 15
    assert regulation_penalty <= 15
    assert result["score"] == 85
    assert result["grade"] == "B"


def test_case4_every_axis_kind_score_zero_grade_f():
    findings = (
        [_finding(rule_id=f"gitleaks:k{i}") for i in range(3)]  # sp = min(40, 45) = 40
        + [
            _reg("R1", "semgrep:kr-r1-browser-geolocation", 15),
            _reg("R2", "semgrep:kr-r2-pii-schema", 15),
            _reg("R3", "semgrep:kr-r3-payment-sdk-js", 12),
            _reg("R5", "semgrep:kr-r5-bulk-messaging", 6),
            _reg("R6", "semgrep:kr-r6-genai-api", 12),
            _reg("R7", "semgrep:kr-r7-rrn-keyword", 20),
        ]  # Σ min(cap, w) = 15+15+12+6+12+20 = 80 → rp = 40
        + [
            _finding(
                axis="license",
                rule_id="license:left-pad",
                severity="high",
                snippet="GPL-3.0",
                weight=10,
            )
            for _ in range(2)  # lp = min(20, 20) = 20
        ]
    )

    result = compute(findings, CATALOG)

    assert result["score"] == 0
    assert result["grade"] == "F"
    assert result["detail"] == {"security": 0, "regulation": 0, "license": 0}


def test_case5_twenty_test_scope_findings_score_100():
    findings = [_finding(scope="test", rule_id=f"gitleaks:t{i}") for i in range(20)]

    result = compute(findings, CATALOG)

    assert result["score"] == 100
    assert result["grade"] == "A"


def test_case6_thirty_same_ruleid_gitleaks_penalty_15_one_finding():
    # §6:237 "gitleaks 같은 RuleID 30건→15+1": the >5 same-RuleID collapse is
    # scanner-level (regression: test_pipeline_fake.py collapse test) — run the
    # 30 raw report entries through the real collapse, then score the result.
    entries = [
        {
            "RuleID": "aws-key",
            "Secret": f"sk-secret-{i}",
            "File": f"f{i}.js",
            "StartLine": i,
            "EndLine": i,
        }
        for i in range(30)
    ]

    findings = gitleaks._parse_report(entries)
    result = compute(findings, CATALOG)

    assert len(findings) == 1  # 30 raw → 1 stored finding
    assert 40 - result["detail"]["security"] == 15  # security_penalty == 15
    assert result["score"] == 85
    assert result["grade"] == "B"


def test_r1_confidence_high_only_when_both_signals_present():
    both = [
        _reg("R1", "semgrep:kr-r1-browser-geolocation", 8),
        _reg("R1", "semgrep:kr-r1-geo-column", 4),
    ]
    one = [both[0]]

    assert {f["confidence"] for f in apply_confidence_rules(both)} == {"high"}
    assert {f["confidence"] for f in apply_confidence_rules(one)} == {"medium"}


def test_r2_confidence_by_distinct_pii_field_types():
    schema_email = _reg("R2", "semgrep:kr-r2-pii-schema", 10, snippet="email = Column(String)")
    schema_phone = _reg(
        "R2", "semgrep:kr-r2-pii-schema", 10, snippet="phone_number = Column(String)"
    )
    hint = _reg("R2", "semgrep:kr-r2-pii-hint", 2)

    two_types = apply_confidence_rules([schema_email, dict(schema_phone)])
    one_type = apply_confidence_rules([schema_email])
    hint_only = apply_confidence_rules([hint])

    assert {f["confidence"] for f in two_types if f["rule_id"] == "semgrep:kr-r2-pii-schema"} == {
        "high"
    }
    assert {f["confidence"] for f in one_type} == {"medium"}
    assert hint_only[0]["confidence"] == "low"
    assert hint_only[0]["weight"] == 2


def test_compute_does_not_mutate_input_findings():
    findings = [_reg("R1", "semgrep:kr-r1-browser-geolocation", 8)]

    compute(findings, CATALOG)

    assert findings[0]["confidence"] == "medium"  # input copy untouched
