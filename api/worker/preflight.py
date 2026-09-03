"""GitHub preflight — SPEC §5.1 + §4.3 rejection rules (frozen Korean messages).

Raises RejectedScan (→ status='rejected') or ScanFailure (→ status='failed');
RetryableGitHubRateLimit is caught by the pipeline, which sleeps 60s and retries once.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings

API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 15

# §4.3:169 — components excluded from the file-count calculation.
EXCLUDED_COMPONENTS = frozenset(
    {".git", "node_modules", "vendor", "dist", "build", ".next", "out", "target", "__pycache__"}
)


class RejectedScan(Exception):
    """Policy rejection (§4.3) — pipeline maps to status='rejected' + error=message."""


class ScanFailure(Exception):
    """Infrastructure/transient failure — pipeline maps to status='failed' + error=message."""


class RetryableGitHubRateLimit(Exception):
    """403 + X-RateLimit-Remaining: 0 — pipeline sleeps 60s and retries once (§4.3)."""


@dataclass(frozen=True, slots=True)
class PreflightResult:
    size_kb: int
    default_branch: str
    commit_sha: str
    file_count: int


def _token() -> str:
    token = Settings().github_token
    if not token:
        raise ScanFailure("GITHUB_TOKEN이 설정되지 않았습니다")
    return token


def _get(client: httpx.Client, url: str, token: str) -> httpx.Response:
    try:
        resp = client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
    except httpx.HTTPError as exc:
        raise ScanFailure("저장소를 확인할 수 없습니다") from exc
    if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
        raise RetryableGitHubRateLimit
    return resp


def is_excluded(path: str) -> bool:
    return any(part in EXCLUDED_COMPONENTS for part in path.split("/"))


def enforce_limits(
    file_count: int, total_bytes: int, largest_bytes: int, *, truncated: bool = False
) -> None:
    """§4.3 verdicts — shared by the preflight tree check and the clone ls-tree re-check."""
    settings = Settings()
    if file_count == 0:
        raise RejectedScan("스캔할 파일이 없습니다(빈 저장소)")
    if truncated or file_count > settings.max_files:
        raise RejectedScan("파일이 3,000개를 넘어 지원하지 않습니다(v1.1 예정)")
    if (
        largest_bytes > settings.max_file_mb * 1024 * 1024
        or total_bytes > settings.max_total_mb * 1024 * 1024
    ):
        raise RejectedScan("저장소 용량이 상한을 넘습니다")


def run_preflight(owner: str, repo: str) -> PreflightResult:
    token = _token()
    with httpx.Client(base_url=API_BASE, timeout=REQUEST_TIMEOUT) as client:
        resp = _get(client, f"/repos/{owner}/{repo}", token)
        if resp.status_code == 404:
            raise RejectedScan("공개 GitHub 저장소만 지원합니다")
        if resp.status_code != 200:
            raise ScanFailure("저장소를 확인할 수 없습니다")
        payload = resp.json()
        if payload.get("private"):
            raise RejectedScan("공개 GitHub 저장소만 지원합니다")

        branch = payload["default_branch"]
        commit_resp = _get(client, f"/repos/{owner}/{repo}/commits/{branch}", token)
        if commit_resp.status_code != 200:
            raise ScanFailure("저장소를 확인할 수 없습니다")
        commit_sha = commit_resp.json()["sha"]

        tree_resp = _get(client, f"/repos/{owner}/{repo}/git/trees/{commit_sha}?recursive=1", token)
        if tree_resp.status_code != 200:
            raise ScanFailure("저장소를 확인할 수 없습니다")
        tree: list[dict[str, Any]] = tree_resp.json().get("tree", [])
        truncated = bool(tree_resp.json().get("truncated", False))

    blobs = [e for e in tree if e.get("type") == "blob"]
    file_count = sum(1 for e in blobs if not is_excluded(e["path"]))
    sizes = [int(e.get("size") or 0) for e in blobs]
    enforce_limits(file_count, sum(sizes), max(sizes, default=0), truncated=truncated)
    return PreflightResult(
        size_kb=int(payload.get("size") or 0),
        default_branch=branch,
        commit_sha=commit_sha,
        file_count=file_count,
    )
