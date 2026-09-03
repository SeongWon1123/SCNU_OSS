"""Semgrep 룰 회귀 테스트 (PROMPTS.md:107 — B 소유 파일, plan todo 8에서 조기 생성).

생성 허용 근거: PROMPTS.md:107(이 파일은 B 소유라 생성 허용) +
00_DECISIONS.md:15(문서 우선순위 03 > 05) — Phase 3에서 만들 예정이었으나
Gate 0 CI rules 잡이 필요로 하므로 조기 생성한다.

sample/positive에 form.js를 추가한 것은 사용자 승인(Q1, 2026-09-03)에 근거한
PROMPTS.md:103(sample 수정 금지)·:192(GLM 양성 추가 권한 없음)의 명시적 예외다.

단독 실행 가능 설계: subprocess + json + pathlib만 사용(app 임포트 없음) —
`docker compose run --rm -w /repo api pytest -q api/tests/test_semgrep_rules.py`
(/repo는 읽기 전용 리포 마운트)에서 그대로 동작한다.

단정 규칙: 룰별 ≥1만 단정한다. 총건수는 단정하지 않는다(샘플 추가 시 변한다).
"""

import json
import subprocess
from pathlib import Path

SEMGREP_CONFIG = Path("/repo/rules/kr-regulation.yaml")
SEMGREP_TIMEOUT_SEC = 300

# PROMPTS.md:107 — 11개 룰 id. 순서는 kr-regulation.yaml 선언 순서.
EXPECTED_RULE_IDS = [
    "kr-r1-browser-geolocation",
    "kr-r1-geo-column",
    "kr-r2-pii-schema",
    "kr-r2-pii-hint",
    "kr-r2-analytics-sdk",
    "kr-r3-payment-sdk-js",
    "kr-r3-payment-sdk-python",
    "kr-r5-bulk-messaging",
    "kr-r6-genai-api",
    "kr-r7-rrn-keyword",
    "kr-r7-rrn-literal",
]


def _run_semgrep(*targets: str) -> list[dict]:
    """semgrep을 실행하고 results 배열을 반환한다.

    semgrep은 finding이 있으면 exit 1, 없으면 exit 0 — 둘 다 성공으로 본다.
    exit >= 2 또는 타임아웃은 에러다.
    """
    proc = subprocess.run(
        [
            "semgrep",
            "scan",
            "--config",
            str(SEMGREP_CONFIG),
            "--json",
            "--metrics=off",
            "--disable-version-check",
            *targets,
        ],
        capture_output=True,
        text=True,
        timeout=SEMGREP_TIMEOUT_SEC,
        check=False,  # returncode 0/1 모두 성공으로 수용(61행) — 동작 불변, PLW1510 명시화
    )
    if proc.returncode not in (0, 1):
        raise AssertionError(
            f"semgrep failed (exit {proc.returncode}) on {targets}\n"
            f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
        )
    return json.loads(proc.stdout).get("results", [])


def _counts_by_rule(results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        # semgrep 1.176.0은 로컬 config 룰 id 앞에 config 디렉터리 접두사를 붙인다
        # (예: "rules.kr-r2-pii-hint") — 마지막 점 뒤의 순수 룰 id로 정규화한다.
        rule_id = result["check_id"].rsplit(".", 1)[-1]
        counts[rule_id] = counts.get(rule_id, 0) + 1
    return counts


def test_positive_sample_each_rule_fires_at_least_once():
    results = _run_semgrep("/repo/sample/positive")
    counts = _counts_by_rule(results)
    for rule_id in EXPECTED_RULE_IDS:
        assert counts.get(rule_id, 0) >= 1, (
            f"{rule_id}: 0 findings on sample/positive (counts={counts})"
        )


def test_negative_sample_zero_findings():
    results = _run_semgrep("/repo/sample/negative")
    assert results == [], f"sample/negative must yield 0 findings, got {results}"


def test_self_scan_rules_and_docs_zero_findings():
    results = _run_semgrep("/repo/rules", "/repo/docs")
    assert results == [], f"rules/ + docs/ self-scan must yield 0 findings, got {results}"
