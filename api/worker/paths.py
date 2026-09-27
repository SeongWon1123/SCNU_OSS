"""Rules directory resolver: REPODOC_RULES_DIR, else the image's /app/rules, else <repo>/rules."""

import os
from pathlib import Path

APP_RULES_DIR = Path("/app/rules")
REPO_RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def rules_dir() -> Path:
    override = os.environ.get("REPODOC_RULES_DIR")
    if override:
        return Path(override)
    if APP_RULES_DIR.is_dir():
        return APP_RULES_DIR
    return REPO_RULES_DIR
