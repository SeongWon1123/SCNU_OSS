"""Hardened clone — SPEC §5.2:181-188 exact command sequence into /scan/<scan_id>.

RLIMIT_AS 1.2GB + RLIMIT_CPU 150 apply to the clone/git subprocesses ONLY (⑥:
semgrep in Phase 2-b relies on --max-memory instead — SPEC.md:309 deviation).
"""

import os
import resource
import shutil
import subprocess

from worker.preflight import ScanFailure, enforce_limits, is_excluded

SCAN_ROOT = "/scan"
CLONE_TIMEOUT = 60
RLIMIT_AS_BYTES = int(1.2 * 1024**3)
RLIMIT_CPU_SECONDS = 150

# §5.2:185 — repo-side ignore files removed before scanners run (Phase 2-b).
STRIP_FILES = (".semgrepignore", ".gitleaksignore", ".gitleaks.toml")


def _apply_rlimits() -> None:  # pragma: no cover — runs in the forked git child
    resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_AS_BYTES, RLIMIT_AS_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (RLIMIT_CPU_SECONDS, RLIMIT_CPU_SECONDS))


def scan_path(scan_id: str) -> str:
    return os.path.join(SCAN_ROOT, str(scan_id))


def _remove(path: str) -> None:
    if not path.startswith(SCAN_ROOT + "/"):
        raise RuntimeError(f"clone path guard violated: {path!r} outside {SCAN_ROOT}/")
    shutil.rmtree(path, ignore_errors=True)


# §5.2:181 hardening flags. Process-level `-c` does NOT persist into the cloned
# repo's config, and checkout runs as a separate process (--no-checkout), so the
# trio is repeated on every git subprocess — measured: without it, checkout
# materializes real symlinks (⑥ deviation note, PR body).
HARDENING_CONFIG = (
    "-c",
    "core.symlinks=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.longpaths=false",
)


def _run(cmd: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT,
            preexec_fn=_apply_rlimits,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScanFailure("저장소 복제 시간 초과") from exc


def git_clone(url: str, path: str) -> None:
    """§5.2:181-182 — hardened no-checkout clone (arg list, never shell=True)."""
    proc = _run(
        [
            "git",
            *HARDENING_CONFIG,
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--no-tags",
            "--no-checkout",
            url,
            path,
        ]
    )
    if proc.returncode != 0:
        raise ScanFailure("저장소를 확인할 수 없습니다")


def ls_tree(path: str) -> list[tuple[str, int]]:
    """§5.2:183 — `git ls-tree -r -l HEAD` → (path, size) blob entries."""
    proc = _run(["git", *HARDENING_CONFIG, "-C", path, "ls-tree", "-r", "-l", "HEAD"])
    if proc.returncode != 0:
        raise ScanFailure("저장소를 확인할 수 없습니다")
    entries: list[tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        meta, _, name = line.partition("\t")
        parts = meta.split()
        if len(parts) < 4:
            continue
        entries.append((name, int(parts[3]) if parts[3].isdigit() else 0))
    return entries


def check_ls_tree(entries: list[tuple[str, int]]) -> None:
    """§4.3 re-check before checkout: count (exclusion list applied) + size caps."""
    counted = sum(1 for name, _ in entries if not is_excluded(name))
    sizes = [size for _, size in entries]
    enforce_limits(counted, sum(sizes), max(sizes, default=0))


def checkout(path: str) -> None:
    """§5.2:184 — `git checkout --quiet HEAD` (symlinks stay materialized as files)."""
    proc = _run(["git", *HARDENING_CONFIG, "-C", path, "checkout", "--quiet", "HEAD"])
    if proc.returncode != 0:
        raise ScanFailure("저장소를 확인할 수 없습니다")


def strip_ignores(path: str) -> list[str]:
    """§5.2:185 — rm -f the three ignore files; return the names actually removed."""
    stripped = []
    for name in STRIP_FILES:
        target = os.path.join(path, name)
        if os.path.lexists(target):
            os.remove(target)
            stripped.append(name)
    return stripped


def clone_repo(url: str, scan_id: str) -> list[str]:
    """Full §5.2 sequence; returns meta.stripped_files. Always removes /scan/<scan_id>."""
    path = scan_path(scan_id)
    try:
        git_clone(url, path)
        check_ls_tree(ls_tree(path))
        checkout(path)
        return strip_ignores(path)
    finally:
        _remove(path)
