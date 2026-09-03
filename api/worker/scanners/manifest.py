"""Manifest scanner — SPEC §5.5:214-217.

package.json(deps+devDeps), requirements.txt, pyproject.toml, Pipfile → dep list,
matched against catalog.yaml dependency_signals (rule_id=manifest:<pkg>, weight 4).
Licenses are display-only: package.json `license` field + rules/license-cache.json
(todo 15 generates it — until then the license step is skipped entirely).
"""

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from worker import catalog as catalog_mod
from worker.clone import scan_path
from worker.scanners import ScannerResult

RULES_DIR = "/app/rules"
MANIFEST_NAMES = ("package.json", "requirements.txt", "pyproject.toml", "Pipfile")
SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    "out",
    "target",
    "__pycache__",
    ".venv",
    "venv",
}

REGULATION_WEIGHT = 4
COPYLEFT_FAMILIES = ("GPL", "AGPL", "LGPL")
COPYLEFT_WEIGHT = 10
UNKNOWN_LICENSE_WEIGHT = 2

# PEP 508 / requirements name separators (extras, version specs, markers, direct refs).
_NAME_SPLIT = re.compile(r"[\[=<>!~;@]")
_PEP503 = re.compile(r"[-_.]+")


def _normalize(name: str) -> str:
    """PEP 503 normalization so `google_generative_ai` matches `google-generativeai`."""
    return _PEP503.sub("-", name).strip().lower()


def _iter_manifests(source: str) -> list[str]:
    found: list[str] = []
    for root, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for name in files:
            if name in MANIFEST_NAMES:
                found.append(os.path.join(root, name))
    return sorted(found)


def _requirements_deps(path: str) -> list[str]:
    deps: list[str] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        name = line.strip()
        if not name or name.startswith(("#", "-")):
            continue
        deps.append(_NAME_SPLIT.split(name, 1)[0].strip())
    return deps


def _pyproject_deps(path: str) -> list[str]:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return []  # a broken manifest is not a regulation signal
    project = data.get("project") or {}
    deps = [str(d) for d in project.get("dependencies") or []]
    for extra in (project.get("optional-dependencies") or {}).values():
        deps.extend(str(d) for d in extra)
    return [_NAME_SPLIT.split(d, 1)[0].strip() for d in deps]


def _pipfile_deps(path: str) -> list[str]:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return []
    deps: list[str] = []
    for section in ("packages", "dev-packages"):
        deps.extend((data.get(section) or {}).keys())
    return deps


def _package_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _deps_for(path: str) -> tuple[list[str], dict[str, Any] | None]:
    name = os.path.basename(path)
    if name == "package.json":
        data = _package_json(path)
        if data is None:
            return [], None
        deps: list[str] = []
        for section in ("dependencies", "devDependencies"):
            deps.extend((data.get(section) or {}).keys())
        return deps, data
    if name == "requirements.txt":
        return _requirements_deps(path), None
    if name == "pyproject.toml":
        return _pyproject_deps(path), None
    return _pipfile_deps(path), None


def _line_of(lines: list[str], pkg: str) -> int | None:
    for idx, line in enumerate(lines, start=1):
        if pkg in line:
            return idx
    return None


def _license_weight(license_str: str) -> int | None:
    """GPL/AGPL/LGPL → 10, unknown → 2, known permissive → None (만점, §5.5:217)."""
    upper = license_str.upper()
    if any(family in upper for family in COPYLEFT_FAMILIES):
        return COPYLEFT_WEIGHT
    if upper in ("", "UNKNOWN", "UNKNOWN LICENSE", "NOASSERTION", "NONE", "UNLICENSED"):
        return UNKNOWN_LICENSE_WEIGHT
    return None


def _load_license_cache() -> dict[str, str] | None:
    path = os.path.join(RULES_DIR, "license-cache.json")
    if not os.path.exists(path):  # todo 15 generates it — skip the license step (§5.5)
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _license_finding(
    rule_id: str, pkg: str, license_str: str, rel_path: str, line: int | None, weight: int
) -> dict[str, Any]:
    if weight == COPYLEFT_WEIGHT:
        title_ko = f"카피레프트 라이선스 패키지가 사용되고 있습니다({pkg}: {license_str})"
    else:
        title_ko = f"라이선스를 확인할 수 없는 패키지가 있습니다({pkg}: {license_str})"
    return {
        "axis": "license",
        "scope": "app",
        "rule_id": rule_id,
        "reg_rule": None,
        "severity": "high" if weight == COPYLEFT_WEIGHT else "low",
        "confidence": None,
        "file_path": rel_path,
        "line_start": line,
        "line_end": line,
        "snippet": license_str,
        "title_ko": title_ko,
        "weight": weight,
    }


def run(scan_id: str) -> ScannerResult:
    source = scan_path(scan_id)
    catalog = catalog_mod.load()
    signal_map: dict[str, str] = {}
    for rule in catalog:
        for signal in catalog_mod.dependency_signals(catalog, rule):
            signal_map.setdefault(_normalize(signal), rule)

    license_cache = _load_license_cache()
    findings: list[dict[str, Any]] = []

    for path in _iter_manifests(source):
        rel_path = os.path.relpath(path, source)
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        deps, package_json = _deps_for(path)
        seen_deps: set[str] = set()

        for pkg in deps:
            if not pkg or pkg in seen_deps:
                continue
            seen_deps.add(pkg)
            line = _line_of(lines, pkg)

            rule = signal_map.get(_normalize(pkg))
            if rule:
                findings.append(
                    {
                        "axis": "regulation",
                        "scope": "app",
                        "rule_id": f"manifest:{pkg}",
                        "reg_rule": rule,
                        "severity": "medium",
                        "confidence": "medium",
                        "file_path": rel_path,
                        "line_start": line,
                        "line_end": line,
                        "snippet": pkg,
                        "title_ko": f"규제 검토가 필요한 패키지가 사용되고 있습니다({pkg})",
                        "weight": REGULATION_WEIGHT,
                    }
                )

            if license_cache is not None:
                declared = license_cache.get(pkg) or license_cache.get(_normalize(pkg))
                if declared is not None:
                    weight = _license_weight(str(declared))
                    if weight is not None:
                        findings.append(
                            _license_finding(
                                f"license:{pkg}", pkg, str(declared), rel_path, line, weight
                            )
                        )

        if package_json is not None:
            declared = package_json.get("license")
            if isinstance(declared, str) and license_cache is not None:
                weight = _license_weight(declared)
                if weight is not None:
                    line = _line_of(lines, "license")
                    findings.append(
                        _license_finding("license:repo", "repo", declared, rel_path, line, weight)
                    )

    return ScannerResult(findings=findings)
