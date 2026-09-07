"""이전 리포 301 추종 — 최종 full_name으로 정규화한다. respx 사용, DB 없음."""

import httpx
import respx

from worker import preflight as preflight_mod


def test_renamed_repo_followed_and_normalized(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    sha = "b" * 40
    tree = [{"type": "blob", "path": "a.py", "size": 10}]
    with respx.mock:
        respx.get("https://api.github.com/repos/old/repo").mock(
            return_value=httpx.Response(
                301,
                headers={"location": "/repos/new/name"},
                json={"message": "Moved Permanently"},
            )
        )
        respx.get("https://api.github.com/repos/new/name").mock(
            return_value=httpx.Response(
                200,
                json={
                    "private": False,
                    "size": 1,
                    "default_branch": "main",
                    "full_name": "new/name",
                },
            )
        )
        respx.get("https://api.github.com/repos/new/name/commits/main").mock(
            return_value=httpx.Response(200, json={"sha": sha})
        )
        respx.get(f"https://api.github.com/repos/new/name/git/trees/{sha}").mock(
            return_value=httpx.Response(200, json={"truncated": False, "tree": tree})
        )
        result = preflight_mod.run_preflight("old", "repo")
    assert result.commit_sha == sha
    assert result.default_branch == "main"
    assert result.file_count == 1


def test_normal_repo_unchanged_without_full_name(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    sha = "c" * 40
    tree = [{"type": "blob", "path": "a.py", "size": 10}]
    with respx.mock:
        respx.get("https://api.github.com/repos/o/r").mock(
            return_value=httpx.Response(
                200, json={"private": False, "size": 1, "default_branch": "main"}
            )
        )
        respx.get("https://api.github.com/repos/o/r/commits/main").mock(
            return_value=httpx.Response(200, json={"sha": sha})
        )
        respx.get(f"https://api.github.com/repos/o/r/git/trees/{sha}").mock(
            return_value=httpx.Response(200, json={"truncated": False, "tree": tree})
        )
        result = preflight_mod.run_preflight("o", "r")
    assert result.commit_sha == sha
    assert result.file_count == 1
