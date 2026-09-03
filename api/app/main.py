"""repodoc API entrypoint."""

from fastapi import FastAPI

from app.routers import badge, health, scans, stats

app = FastAPI(title="repodoc")
app.include_router(health.router)
# /recent must be declared before /{scan_id} — routers/scans.py orders its routes.
app.include_router(scans.router)
app.include_router(stats.router)
app.include_router(badge.router)
