"""gitleaks scanner — SPEC §5.3:192-197, command and flags frozen."""

import json
import os
import subprocess
from typing import Any

from worker.clone import scan_path
from worker.preflight import ScanFailure
from worker.scanners import ScannerResult

TIMEOUT = 60
RULES_CONFIG = "/app/rules/gitleaks.toml"
REPORT_NAME = "gitleaks-report.json"
COLLAPSE_THRESHOLD = 5  # same RuleID >5 occurrences → collapse to 1 finding
WEIGHT = 15

FAILURE_MESSAGE = "정적 분석에 실패했습니다"
TIMEOUT_MESSAGE = "분석 시간 초과"


def _command(source: str, report: str) -> list[str]:
    return [
        "gitleaks",
        "detect",
        "--source",
        source,
        "--no-git",
        "--config",
        RULES_CONFIG,
        "--gitleaks-ignore-path",
        "/dev/null",
        "--max-target-megabytes",
        "1",
        "--report-format",
        "json",
        "--report-path",
        report,
        "--exit-code",
        "0",
    ]


def _version() -> str:
    proc = subprocess.run(
        ["gitleaks", "version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    out = (proc.stdout or proc.stderr).strip()
    return out.splitlines()[-1] if out else "unknown"


def _mask(secret: str) -> str:
    """앞 2자 + **** — the raw secret is never stored or logged (AGENTS.md 규칙 3)."""
    return secret[:2] + "****"


def _parse_report(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report JSON → finding dicts. Same RuleID >COLLAPSE_THRESHOLD → 1 finding
    (weight stays 15; the scoring cap handles the rest — SPEC §6)."""
    per_rule: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        per_rule.setdefault(str(entry.get("RuleID", "")), []).append(entry)

    findings: list[dict[str, Any]] = []
    for rule_id, group in per_rule.items():
        kept = group[:1] if len(group) > COLLAPSE_THRESHOLD else group
        for entry in kept:
            findings.append(
                {
                    "axis": "security",
                    "scope": "app",
                    "rule_id": f"gitleaks:{rule_id}",
                    "reg_rule": None,
                    "severity": "critical",
                    "confidence": None,
                    "file_path": entry.get("File"),
                    "line_start": entry.get("StartLine"),
                    "line_end": entry.get("EndLine"),
                    "snippet": _mask(str(entry.get("Secret", ""))),
                    "title_ko": f"시크릿이 커밋된 것으로 보입니다({rule_id})",
                    "weight": WEIGHT,
                }
            )
    return findings


def run(scan_id: str) -> ScannerResult:
    source = scan_path(scan_id)
    report = os.path.join(source, REPORT_NAME)
    try:
        proc = subprocess.run(
            _command(source, report),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScanFailure(TIMEOUT_MESSAGE) from exc
    if proc.returncode != 0:
        raise ScanFailure(FAILURE_MESSAGE)

    with open(report, encoding="utf-8") as f:
        entries = json.load(f)
    findings = _parse_report(entries)
    # Removed here, not only in the pipeline finally: semgrep runs next on the
    # same directory and must never see the report's raw secrets (AGENTS.md 규칙 3).
    os.remove(report)
    return ScannerResult(findings=findings, tools={"gitleaks": _version()})
