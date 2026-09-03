"""Shared test fixtures — real Postgres via deps.engine (compose db service)."""

import pytest
from sqlalchemy import text

from app import deps
from app.models import Base


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> None:
    Base.metadata.create_all(deps.engine)


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    # Truncate BEFORE each test (setup time): deps.engine is guaranteed to be the
    # real Postgres engine here, while per-test teardown order with test_health's
    # monkeypatched sqlite engine is not something to rely on.
    with deps.engine.begin() as conn:
        conn.execute(text("TRUNCATE findings, scans, rate_limit_hits RESTART IDENTITY CASCADE"))
    yield
