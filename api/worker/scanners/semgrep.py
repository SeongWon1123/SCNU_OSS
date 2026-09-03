"""semgrep scanner — SPEC §5.4:199-212, command and flags frozen."""

import json
import os
import re
import subprocess
from fnmatch import fnmatch
from typing import Any

from worker.clone import scan_path
from worker.preflight import ScanFailure
from worker.scanners import ScannerResult

TIMEOUT = 120
RULES_DIR = "/app/rules"
MAX_SNIPPET_CHARS = 300
PER_RULE_LIMIT = 200

FAILURE_MESSAGE = "정적 분석에 실패했습니다"
TIMEOUT_MESSAGE = "분석 시간 초과"

# §5.4:211 scope=test patterns (repo-relative paths).
TEST_PATH_RE = re.compile(r"^(sample|samples|fixtures|__fixtures__|test|tests|__tests__|spec|e2e)/")
TEST_FILE_PATTERNS = ("*.test.*", "*.spec.*", "*_test.*", "test_*.py")

# §5.4:208 — semgrep severity → (severity label, weight).
SEVERITY_MAP = {"ERROR": ("high", 8), "WARNING": ("medium", 3), "INFO": ("low", 1)}


def _command(source: str) -> list[str]:
    configs: list[str] = []
    p_ci = f"{RULES_DIR}/vendor/p-ci.yaml"
    if os.path.exists(p_ci):  # Gate-1 fallback record → kr-only (SPEC.md:212)
        configs += ["--config", p_ci]
    configs += ["--config", f"{RULES_DIR}/kr-regulation.yaml"]
    return [
        "semgrep",
        "scan",
        *configs,
        "--json",
        "--metrics=off",
        "--disable-version-check",
        "--no-git-ignore",
        "--timeout",
        "5",
        "--timeout-threshold",
        "3",
        "--max-target-bytes",
        "1000000",
        "--max-memory",
        "1000",
        "-j",
        "2",
        "--exclude",
        "node_modules",
        "--exclude",
        ".git",
        "--exclude",
        "vendor",
        "--exclude",
        "dist",
        "--exclude",
        "build",
        "--exclude",
        ".next",
        source,
    ]


def _raise_for_exit(returncode: int) -> None:
    """수정 #5: exit 0 and 1 are both success (1 = findings found); ≥2 is a failure."""
    if returncode >= 2:
        raise ScanFailure(FAILURE_MESSAGE)


def _is_test_scope(path: str) -> bool:
    posix = path.replace(os.sep, "/")
    if TEST_PATH_RE.match(posix):
        return True
    name = os.path.basename(posix)
    return any(fnmatch(name, pattern) for pattern in TEST_FILE_PATTERNS)


def _snippet(source: str, rel_path: str, start: int, end: int) -> str:
    full = os.path.join(source, rel_path)
    with open(full, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return "".join(lines[start - 1 : end])[:MAX_SNIPPET_CHARS]


def _build_finding(source: str, result: dict[str, Any]) -> dict[str, Any]:
    check_id = str(result.get("check_id", ""))
    # semgrep 1.176.0 prefixes local-config ids with the config dir (e.g.
    # "rules.kr-r2-pii-hint") — the last dot segment is the stable id (SPEC §5.4:209).
    rule_id = "semgrep:" + check_id.rsplit(".", 1)[-1]
    rel_path = str(result.get("path", ""))
    start = int(result.get("start", {}).get("line", 0))
    end = int(result.get("end", {}).get("line", start))

    extra = result.get("extra") or {}
    metadata = extra.get("metadata") or {}
    reg_rule = metadata.get("rule")
    severity_raw = str(extra.get("severity", "INFO")).upper()
    scope = "test" if _is_test_scope(rel_path) else "app"

    if reg_rule:
        axis = "regulation"
        severity = SEVERITY_MAP.get(severity_raw, ("low", 1))[0]
        weight = int(metadata.get("weight", 0))
        confidence = metadata.get("confidence")
        title_ko = str(extra.get("message") or f"규제 관련 코드가 발견되었습니다({reg_rule})")
    else:
        axis = "security"
        severity, weight = SEVERITY_MAP.get(severity_raw, ("low", 1))
        confidence = None
        tail = rule_id.split(":", 1)[-1]
        title_ko = f"보안 규칙에 해당하는 코드가 발견되었습니다({tail})"
    if scope == "test":
        weight = 0

    return {
        "axis": axis,
        "scope": scope,
        "rule_id": rule_id,
        "reg_rule": reg_rule,
        "severity": severity,
        "confidence": confidence,
        "file_path": rel_path,
        "line_start": start,
        "line_end": end,
        "snippet": _snippet(source, rel_path, start, end),
        "title_ko": title_ko,
        "weight": weight,
    }


def _parse(source: str, payload: dict[str, Any]) -> ScannerResult:
    findings: list[dict[str, Any]] = []
    truncated: dict[str, int] = {}
    seen: set[tuple[str, str, int]] = set()
    per_rule_count: dict[str, int] = {}

    for result in payload.get("results", []):
        check_id = str(result.get("check_id", ""))
        rule_id = "semgrep:" + check_id.rsplit(".", 1)[-1]
        rel_path = str(result.get("path", ""))
        start = int(result.get("start", {}).get("line", 0))
        key = (rule_id, rel_path, start)
        if key in seen:  # dedupe key (rule_id, path, start.line) — SPEC §5.4:209
            continue
        seen.add(key)

        if per_rule_count.get(rule_id, 0) >= PER_RULE_LIMIT:
            truncated[rule_id] = truncated.get(rule_id, 0) + 1
            continue
        per_rule_count[rule_id] = per_rule_count.get(rule_id, 0) + 1
        findings.append(_build_finding(source, result))

    version = str(payload.get("version") or "unknown")
    return ScannerResult(findings=findings, truncated=truncated, tools={"semgrep": version})


def run(scan_id: str) -> ScannerResult:
    source = scan_path(scan_id)
    try:
        proc = subprocess.run(
            _command(source),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScanFailure(TIMEOUT_MESSAGE) from exc
    _raise_for_exit(proc.returncode)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ScanFailure(FAILURE_MESSAGE) from exc
    return _parse(source, payload)
