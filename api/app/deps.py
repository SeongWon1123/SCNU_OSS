"""Shared dependencies: DB engine re-export + connectivity probe + settings provider.

`engine` is re-exported here (not defined) so test_health's
`monkeypatch.setattr(deps, "engine", ...)` keeps patching the one global that
check_db() reads.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import SessionLocal, engine  # noqa: F401  (re-export)


def check_db() -> bool:
    """Lightweight connectivity probe: SELECT 1. False when the DB is unreachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def get_settings() -> Settings:
    return Settings()
