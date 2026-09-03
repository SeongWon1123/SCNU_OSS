"""SPEC §6:224-237 — deterministic score, pure function, LLM-free.

compute(findings, catalog) -> {"score", "grade", "detail"}:
  scope='test' findings weigh 0 (display only);
  security_penalty   = min(40, Σ security weight)
  regulation_penalty = min(40, Σ_R min(catalog[R].weight_cap, Σ weight of R))
  license_penalty    = min(20, Σ license weight)
  score = max(0, 100 - security_penalty - regulation_penalty - license_penalty)
  grade = A≥90 B≥75 C≥60 D≥40 F
  detail = {security: 40-sp, regulation: 40-rp, license: 20-lp}  (remaining budget)

apply_confidence_rules implements §6:234-235 (display metadata; the §6 arithmetic
uses weight only): R1 browser-geolocation + geo-column both present → high, one
→ medium; R2 pii-schema ≥2 distinct field types → high, 1 → medium, hint-only
→ low (weight 2). No DB, no I/O.
"""

import re
from typing import Any

SECURITY_CAP = 40
REGULATION_CAP = 40
LICENSE_CAP = 20

R1_BROWSER = "semgrep:kr-r1-browser-geolocation"
R1_GEO_COLUMN = "semgrep:kr-r1-geo-column"
R2_PII_SCHEMA = "semgrep:kr-r2-pii-schema"
R2_PII_HINT = "semgrep:kr-r2-pii-hint"

# kr-r2-pii-schema pattern vocabulary → canonical field type (§6:235 "2종 이상 필드").
_PII_FIELD_RE = re.compile(
    "|".join(
        f"(?P<{name}>{pattern})"
        for pattern, name in (
            (r"e_?mail", "email"),
            (r"phone(?:_number|_no)?", "phone"),
            (r"birth(?:date|day)?", "birth"),
            (r"(?:full|real)_name", "name"),
            (r"address", "address"),
        )
    ),
    re.IGNORECASE,
)


def _pii_field_types(snippet: str | None) -> set[str]:
    if not snippet:
        return set()
    return {m.lastgroup for m in _PII_FIELD_RE.finditer(snippet) if m.lastgroup}


def apply_confidence_rules(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """§6:234-235 — returns adjusted copies; never mutates the input."""
    adjusted = [dict(f) for f in findings]
    reg = [f for f in adjusted if f.get("axis") == "regulation"]

    r1 = [f for f in reg if f.get("reg_rule") == "R1"]
    r1_ids = {f.get("rule_id") for f in r1}
    r1_confidence = "high" if {R1_BROWSER, R1_GEO_COLUMN} <= r1_ids else "medium"
    for f in r1:
        f["confidence"] = r1_confidence

    schema = [f for f in reg if f.get("rule_id") == R2_PII_SCHEMA]
    hint = [f for f in reg if f.get("rule_id") == R2_PII_HINT]
    if schema:
        types: set[str] = set()
        for f in schema:
            types |= _pii_field_types(f.get("snippet"))
        schema_confidence = "high" if len(types) >= 2 else "medium"
        for f in schema:
            f["confidence"] = schema_confidence
    for f in hint:  # hint-only (or alongside schema) stays low at weight 2
        f["confidence"] = "low"
        f["weight"] = 2
    return adjusted


def _weight_cap(catalog: dict[str, Any], rule: str) -> int | None:
    block = catalog.get(rule) or {}
    cap = block.get("weight_cap")
    return int(cap) if cap is not None else None


def _regulation_penalty(scored: list[dict[str, Any]], catalog: dict[str, Any]) -> int:
    per_rule: dict[str, int] = {}
    for f in scored:
        if f["axis"] == "regulation" and f.get("reg_rule"):
            per_rule[f["reg_rule"]] = per_rule.get(f["reg_rule"], 0) + f["weight"]
    capped = 0
    for rule, weight in per_rule.items():
        cap = _weight_cap(catalog, rule)
        capped += weight if cap is None else min(cap, weight)
    return min(REGULATION_CAP, capped)


def compute(findings: list[dict[str, Any]], catalog: dict[str, Any]) -> dict[str, Any]:
    findings = apply_confidence_rules(findings)
    scored = [f for f in findings if f.get("scope") != "test"]

    security_penalty = min(SECURITY_CAP, sum(f["weight"] for f in scored if f["axis"] == "security"))
    regulation_penalty = _regulation_penalty(scored, catalog)
    license_penalty = min(LICENSE_CAP, sum(f["weight"] for f in scored if f["axis"] == "license"))

    score = max(0, 100 - security_penalty - regulation_penalty - license_penalty)
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"
    return {
        "score": score,
        "grade": grade,
        "detail": {
            "security": SECURITY_CAP - security_penalty,
            "regulation": REGULATION_CAP - regulation_penalty,
            "license": LICENSE_CAP - license_penalty,
        },
    }
