"""Static-analysis scanners — SPEC §5.3 (gitleaks), §5.4 (semgrep), §5.5 (manifest).

Each scanner returns a ScannerResult whose finding dicts match the Finding
columns (minus scan_id/id). Raw secrets never leave the gitleaks report file,
which is removed right after parsing (AGENTS.md 규칙 3 — 원문 미저장).
"""

import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any


def repo_rel_path(source: str, path: str) -> str:
    """스캔 루트 기준 상대경로 — UI 표시·scope 판정·dedupe용.

    semgrep·gitleaks는 절대 타깃을 주면 절대경로를 내놓는다(`/scan/<id>/...`).
    소스 밖(`..`)이면 basename으로 축소한다(경로 표시 안전).
    """
    if not path or not os.path.isabs(path):
        return (path or "").replace(os.sep, "/")
    rel = os.path.relpath(path, source)
    if rel == "." or rel == ".." or rel.startswith(".." + os.sep):
        return os.path.basename(path)
    return rel.replace(os.sep, "/")


# SPEC §5.4:211 scope=test 판정(리포 상대경로 전제) — semgrep·gitleaks 공통.
TEST_PATH_RE = re.compile(r"^(sample|samples|fixtures|__fixtures__|test|tests|__tests__|spec|e2e)/")
TEST_FILE_PATTERNS = ("*.test.*", "*.spec.*", "*_test.*", "test_*.py")


def is_test_scope(rel_path: str) -> bool:
    """테스트·샘플 경로면 True (weight 0, 접힘 표시)."""
    posix = rel_path.replace(os.sep, "/")
    if TEST_PATH_RE.match(posix):
        return True
    name = os.path.basename(posix)
    return any(fnmatch(name, pattern) for pattern in TEST_FILE_PATTERNS)


@dataclass(frozen=True, slots=True)
class ScannerResult:
    findings: list[dict[str, Any]]
    truncated: dict[str, int] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
