"""catalog.yaml loader — READ-ONLY (frozen file; AGENTS.md: 사람 B만 수정).

pyyaml is not in the image; ruamel.yaml (safe mode) ships with the pinned
semgrep dependency — no new dependency is added (PR 계약 ④). The frozen file
contains one plain scalar with an interior ': ' (line 5, '신고 창구: ...') which
every strict YAML parser rejects; _repair_plain_scalar_colons quotes such values
without touching the file itself (declared in PR 계약 ⑥).
"""

import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

CATALOG_PATH = Path("/app/rules/catalog.yaml")

_MAPPING_LINE = re.compile(r"^(\s*[\w.-]+: )(.+)$")


def _repair_plain_scalar_colons(text: str) -> str:
    """Quote plain-scalar values containing ': ' (invalid YAML, frozen content)."""
    fixed: list[str] = []
    for line in text.splitlines():
        match = _MAPPING_LINE.match(line)
        if match:
            key, value = match.groups()
            if ": " in value and not value.lstrip().startswith("["):
                if '"' in value:
                    raise ValueError(f"catalog value needs manual quoting: {line!r}")
                line = f'{key}"{value}"'
        fixed.append(line)
    return "\n".join(fixed) + "\n"


def load() -> dict[str, Any]:
    yaml = YAML(typ="safe", pure=True)
    text = CATALOG_PATH.read_text(encoding="utf-8")
    data = yaml.load(_repair_plain_scalar_colons(text))
    return data or {}


def dependency_signals(catalog: dict[str, Any], rule: str) -> list[str]:
    block = catalog.get(rule) or {}
    return list(block.get("dependency_signals") or [])
