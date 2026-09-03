"""repodoc API entrypoint (Phase 0-a skeleton)."""

from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="repodoc")
app.include_router(health.router)
