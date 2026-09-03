"""Hardened-clone regression — SPEC §5.2 DoD 5 cases + 3,000-file/5s mocked case.

Fixtures build LOCAL bare repos (`git init --bare` + worktree commit+push, A7).
GitHub API is mocked (respx) everywhere; no test performs a real API call.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
import respx

from app.db import SessionLocal
from app.models import Scan
from worker import clone
from worker.pipeline import run_scan
from worker.preflight import RejectedScan, ScanFailure

MSG_TOO_MANY = "파일이 3,000개를 넘어 지원하지 않습니다(v1.1 예정)"
MSG_TOO_BIG = "저장소 용량이 상한을 넘습니다"


@pytest.fixture(autouse=True)
def _scan_root():
    """The api test container has no /scan tmpfs (worker-only); create and clean it."""
    os.makedirs(clone.SCAN_ROOT, exist_ok=True)
    yield
    for entry in Path(clone.SCAN_ROOT).iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            entry.unlink()


def _git(work: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True, text=True)


def _bare(tmp_path: Path, name: str) -> tuple[str, Path]:
    """`git init --bare` + worktree commit+push → (clone-url, worktree)."""
    bare = tmp_path / f"{name}.git"
    work = tmp_path / f"{name}-work"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "test")
    return str(bare), work


def _commit_push(work: Path, bare: str, msg: str = "c") -> None:
    _git(work, "add", "-A")
    _git(work, "commit", "-m", msg)
    _git(work, "push", "-q", bare, "main")


def test_1_symlink_repo_materializes_no_symlinks(tmp_path):
    bare, work = _bare(tmp_path, "sym")
    os.symlink("/etc/hostname", work / "link")
    (work / "f.txt").write_text("x")
    _commit_push(work, bare)

    path = clone.scan_path("sym-case")
    clone.git_clone(bare, path)
    clone.check_ls_tree(clone.ls_tree(path))
    clone.checkout(path)
    links = [str(p) for p in Path(path).rglob("*") if os.path.islink(p)]
    assert links == []
    # core.symlinks=false: the symlink entry became a regular file, not a link.
    assert (Path(path) / "link").is_file()
    clone._remove(path)


def test_2_ten_100mb_files_rejected_before_checkout(tmp_path):
    bare, work = _bare(tmp_path, "big")
    for i in range(10):
        with open(work / f"big{i}.bin", "wb") as f:
            f.seek(100 * 1024 * 1024 - 1)
            f.write(b"\0")
    _commit_push(work, bare)

    before = shutil.disk_usage(clone.SCAN_ROOT).free
    with pytest.raises(RejectedScan) as ei:
        clone.clone_repo(bare, "big-case")
    assert str(ei.value) == MSG_TOO_BIG
    # Rejected before checkout: nothing persisted (64MB slack absorbs unrelated
    # filesystem noise; a materialized 1GB worktree would blow far past it).
    assert shutil.disk_usage(clone.SCAN_ROOT).free - before > -(64 * 1024 * 1024)
    assert not os.path.exists(clone.scan_path("big-case"))


def test_3_five_thousand_files_rejected_without_checkout(tmp_path, monkeypatch):
    bare, work = _bare(tmp_path, "many")
    for i in range(5_000):
        (work / f"f{i:05}.txt").write_text("x")
    _commit_push(work, bare)

    checkout_calls: list[str] = []
    monkeypatch.setattr(clone, "checkout", lambda path: checkout_calls.append(path))
    with pytest.raises(RejectedScan) as ei:
        clone.clone_repo(bare, "many-case")
    assert str(ei.value) == MSG_TOO_MANY
    assert checkout_calls == []  # no-checkout held: checkout never ran
    assert not os.path.exists(clone.scan_path("many-case"))


def test_4_semgrepignore_stripped_and_recorded(tmp_path):
    bare, work = _bare(tmp_path, "strip")
    (work / ".semgrepignore").write_text("*\n")
    (work / "code.py").write_text("print(1)\n")
    _commit_push(work, bare)

    assert clone.clone_repo(bare, "strip-case") == [".semgrepignore"]

    # Direct-drive proof that the file is really removed from the checkout.
    path = clone.scan_path("strip-case2")
    clone.git_clone(bare, path)
    clone.check_ls_tree(clone.ls_tree(path))
    clone.checkout(path)
    assert clone.strip_ignores(path) == [".semgrepignore"]
    assert not os.path.exists(os.path.join(path, ".semgrepignore"))
    clone._remove(path)


def test_5_dotdot_filename_git_rejects(tmp_path):
    """`../` filename: real git behavior (container git 2.39) — every crafting route
    is refused at object-creation time, so a clone can never receive such a tree:
      `git mktree`            → fatal: path ../escape contains slash
      `git update-index --cacheinfo` → error: Invalid path '../escape'
    The hardened clone flags are belt-and-suspenders behind git's own defense."""
    bare, work = _bare(tmp_path, "escape")
    (work / "ok.txt").write_text("x")
    _commit_push(work, bare)

    blob = subprocess.run(
        ["git", "-C", bare, "hash-object", "-w", "--stdin"],
        input="x",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    mktree = subprocess.run(
        ["git", "-C", bare, "mktree"],
        input=f"100644 blob {blob}\t../escape\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert mktree.returncode != 0
    assert "contains slash" in mktree.stderr

    update_index = subprocess.run(
        ["git", "-C", work, "update-index", "--add", "--cacheinfo", f"100644,{blob},../escape"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert update_index.returncode != 0
    assert "Invalid path" in update_index.stderr


def test_6_three_thousand_file_rejection_within_5s(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    tree = [{"type": "blob", "path": f"f{i}.txt", "size": 1} for i in range(3_500)]
    sha = "a" * 40
    with respx.mock:
        respx.get("https://api.github.com/repos/psf/requests").mock(
            return_value=httpx.Response(
                200, json={"private": False, "size": 1, "default_branch": "main"}
            )
        )
        respx.get("https://api.github.com/repos/psf/requests/commits/main").mock(
            return_value=httpx.Response(200, json={"sha": sha})
        )
        respx.get(f"https://api.github.com/repos/psf/requests/git/trees/{sha}").mock(
            return_value=httpx.Response(200, json={"truncated": False, "tree": tree})
        )
        scan = Scan(
            repo_url="https://github.com/psf/requests",
            owner="psf",
            repo="requests",
            owner_token="tok-test6",
        )
        with SessionLocal() as session:
            session.add(scan)
            session.commit()
            scan_id = scan.id

        start = time.monotonic()
        run_scan(scan_id)
        elapsed = time.monotonic() - start

    assert elapsed < 5.0
    with SessionLocal() as session:
        row = session.get(Scan, scan_id)
        assert row is not None
        assert row.status == "rejected"
        assert row.error == MSG_TOO_MANY


def test_7_clone_timeout_maps_to_failed_message(tmp_path, monkeypatch):
    bare, _work = _bare(tmp_path, "slow")

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=60)

    monkeypatch.setattr("worker.clone.subprocess.run", slow_run)
    with pytest.raises(ScanFailure) as ei:
        clone.clone_repo(bare, "slow-case")
    assert str(ei.value) == "저장소 복제 시간 초과"
    assert not os.path.exists(clone.scan_path("slow-case"))
