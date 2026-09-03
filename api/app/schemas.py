"""Pydantic response/request models — SPEC.md §4.2."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ScanCreate(BaseModel):
    repo_url: str
    consent: bool = False
    explain: bool = True
    force: bool = False


class ScanCreated(BaseModel):
    id: UUID
    status: str
    owner_token: str
    queue_position: int


class ScanCached(BaseModel):
    id: UUID
    status: str
    queue_position: int


class ScanLimited(BaseModel):
    id: UUID
    status: str
    score: int | None = None
    grade: str | None = None
    score_detail: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    message: str


class RecentScan(BaseModel):
    owner: str
    repo: str
    score: int | None = None
    grade: str | None = None
