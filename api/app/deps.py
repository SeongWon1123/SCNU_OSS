"""Shared dependencies: DB engine + connectivity probe."""

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings

engine = create_engine(Settings().database_url, pool_pre_ping=True)


def check_db() -> bool:
    """Lightweight connectivity probe: SELECT 1. False when the DB is unreachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
