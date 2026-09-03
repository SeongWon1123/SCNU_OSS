"""Health endpoint tests — no live Postgres needed at this phase.

Reachable DB is simulated with an in-memory SQLite engine; the unreachable case
uses a real engine pointed at a connection-refused endpoint.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import deps
from app.main import app

client = TestClient(app)


def test_health_returns_ok_and_db_true_when_db_reachable(monkeypatch):
    monkeypatch.setattr(deps, "engine", create_engine("sqlite://"))
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "db": True, "worker_seen_at": None}


def test_health_returns_db_false_when_db_unreachable(monkeypatch):
    unreachable = create_engine("postgresql+psycopg://postgres:postgres@127.0.0.1:1/none")
    monkeypatch.setattr(deps, "engine", unreachable)

    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["db"] is False
