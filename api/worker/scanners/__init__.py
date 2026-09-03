"""Static-analysis scanners — SPEC §5.3 (gitleaks), §5.4 (semgrep), §5.5 (manifest).

Each scanner returns a ScannerResult whose finding dicts match the Finding
columns (minus scan_id/id). Raw secrets never leave the gitleaks report file,
which is removed right after parsing (AGENTS.md 규칙 3 — 원문 미저장).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ScannerResult:
    findings: list[dict[str, Any]]
    truncated: dict[str, int] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
