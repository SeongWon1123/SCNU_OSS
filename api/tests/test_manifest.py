"""Manifest scanner regression — SPEC §5.5 dependency_signals + license handling.

Fixtures are written into a fake scan dir; RULES_DIR is monkeypatched to a tmp
dir so the license-cache presence (todo 15 lands it in parallel) cannot flip
assertions. catalog.yaml is loaded from the real frozen /app/rules path.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from worker import clone
from worker.scanners import manifest


@pytest.fixture(autouse=True)
def _scan_root():
    """The api test container has no /scan tmpfs (worker-only); create and clean it."""
    os.makedirs(clone.SCAN_ROOT, exist_ok=True)
    yield
    for entry in Path(clone.SCAN_ROOT).iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink()


@pytest.fixture(autouse=True)
def _rules_dir(tmp_path, monkeypatch):
    rules = tmp_path / "rules"
    rules.mkdir()
    monkeypatch.setattr(manifest, "RULES_DIR", str(rules))
    return rules


def _write(scan_id: str, name: str, content: str) -> None:
    path = Path(clone.scan_path(scan_id))
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(content, encoding="utf-8")


def test_package_json_payment_sdks_match_r3():
    _write(
        "mf-r3",
        "package.json",
        json.dumps(
            {
                "name": "fixture",
                "dependencies": {
                    "@tosspayments/payment-sdk": "^1.0.0",
                    "stripe": "^12.0.0",
                    "express": "^4.18.0",
                },
            }
        ),
    )

    result = manifest.run("mf-r3")

    r3 = [f for f in result.findings if f["axis"] == "regulation"]
    assert {f["rule_id"] for f in r3} == {
        "manifest:@tosspayments/payment-sdk",
        "manifest:stripe",
    }
    for f in r3:
        assert f["reg_rule"] == "R3"
        assert f["weight"] == 4
        assert f["confidence"] == "medium"
        assert f["scope"] == "app"


def test_requirements_txt_openai_matches_r6():
    _write("mf-r6", "requirements.txt", "openai==1.0.0\nrequests>=2.0\n")

    result = manifest.run("mf-r6")

    r6 = [f for f in result.findings if f["axis"] == "regulation"]
    assert len(r6) == 1
    assert r6[0]["rule_id"] == "manifest:openai"
    assert r6[0]["reg_rule"] == "R6"
    assert r6[0]["weight"] == 4


def test_license_cache_absent_skips_license_step():
    _write(
        "mf-nocache",
        "package.json",
        json.dumps(
            {
                "name": "fixture",
                "license": "GPL-3.0",
                "dependencies": {"left-pad": "^1.3.0"},
            }
        ),
    )

    result = manifest.run("mf-nocache")

    assert [f for f in result.findings if f["axis"] == "license"] == []


def test_license_gpl_weight_10_when_cache_present(tmp_path):
    cache = {"left-pad": "GPL-3.0"}
    (tmp_path / "rules" / "license-cache.json").write_text(json.dumps(cache))
    _write(
        "mf-gpl",
        "package.json",
        json.dumps(
            {
                "name": "fixture",
                "license": "GPL-3.0",
                "dependencies": {"left-pad": "^1.3.0"},
            }
        ),
    )

    result = manifest.run("mf-gpl")

    license_findings = [f for f in result.findings if f["axis"] == "license"]
    assert {f["rule_id"] for f in license_findings} == {"license:left-pad", "license:repo"}
    for f in license_findings:
        assert f["axis"] == "license"
        assert f["scope"] == "app"
        assert f["weight"] == 10
        assert f["severity"] == "high"
