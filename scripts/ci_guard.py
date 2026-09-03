"""CI guard — SPEC.md §10 job 6 (PR diff policy).

Pure stdlib. Runs as the `guard` job on pull_request only.
Env:
  GITHUB_BASE_REF (preferred) or BASE_REF — PR base branch name
  B_EMAIL        — the only author email allowed on 사람-B 전용 paths
  PR_LABELS      — comma-joined PR labels; `unlock-approved` unlocks lock files
Exit 0 = pass, 1 = fail (Korean reason lines on stdout).
"""

from __future__ import annotations

import os
import subprocess
import sys

MAX_DIFF_LINES = 400
MAX_DIFF_FILES = 12
UNLOCK_LABEL = "unlock-approved"

# 사람 B만 수정 가능 (AGENTS.md 잠금 파일 중 B 몫).
B_ONLY_PREFIXES = ("rules/",)
B_ONLY_EXACT = ("docs/LAW_REFERENCES.md", "api/tests/test_semgrep_rules.py")

# 잠금 파일 중 A 몫 — unlock-approved 라벨 없이는 못 건드린다.
LOCK_PATHS = ("api/app/db.py", "api/app/models.py", "api/worker/pipeline.py")


def _git(args: list[str], cwd: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {proc.stderr.strip()}")
    return proc.stdout


def resolve_base(env: dict[str, str]) -> str:
    base = env.get("GITHUB_BASE_REF") or env.get("BASE_REF")
    if not base:
        raise RuntimeError("GITHUB_BASE_REF 또는 BASE_REF 환경변수가 없다.")
    return base


def diff_numstat(base: str, cwd: str) -> list[tuple[int, int, str]]:
    """PR diff를 (added, deleted, path) 행으로 반환. base...HEAD 실패 시 base 폴백."""
    try:
        out = _git(["diff", "--numstat", f"{base}...HEAD"], cwd)
    except RuntimeError:
        out = _git(["diff", "--numstat", base], cwd)
    rows: list[tuple[int, int, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        rows.append(
            (
                0 if added == "-" else int(added),
                0 if deleted == "-" else int(deleted),
                path,
            )
        )
    return rows


def commit_author_emails(base: str, cwd: str) -> list[str]:
    """PR 범위(base..HEAD) 커밋의 author 이메일. 실패 시 base...HEAD(대칭차) 폴백."""
    try:
        out = _git(["log", "--format=%ae", f"{base}..HEAD"], cwd)
    except RuntimeError:
        out = _git(["log", "--format=%ae", f"{base}...HEAD"], cwd)
    return [line for line in out.splitlines() if line]


def guard_size(rows: list[tuple[int, int, str]]) -> list[str]:
    lines = sum(added + deleted for added, deleted, _ in rows)
    reasons = []
    if lines > MAX_DIFF_LINES:
        reasons.append(f"PR diff가 {lines}줄 — 상한 {MAX_DIFF_LINES}줄 초과")
    if len(rows) > MAX_DIFF_FILES:
        reasons.append(f"PR diff가 {len(rows)}개 파일 — 상한 {MAX_DIFF_FILES}개 초과")
    return reasons


def guard_tests_not_weakened(rows: list[tuple[int, int, str]]) -> list[str]:
    added = sum(a for a, _, p in rows if p.startswith("api/tests/"))
    deleted = sum(d for _, d, p in rows if p.startswith("api/tests/"))
    if deleted > added:
        return [
            f"api/tests/** 삭제 {deleted}줄 > 추가 {added}줄 — 테스트 완화로 판단해 실패"
        ]
    return []


def guard_b_only(
    rows: list[tuple[int, int, str]], authors: list[str], b_email: str
) -> list[str]:
    touched = [
        p for _, _, p in rows if p.startswith(B_ONLY_PREFIXES) or p in B_ONLY_EXACT
    ]
    if not touched:
        return []
    strangers = sorted({email for email in authors if email != b_email})
    if strangers:
        return [
            f"사람 B 전용 파일 변경({', '.join(touched)})에 B가 아닌 커밋 author 존재: {', '.join(strangers)}"
        ]
    return []


def guard_unlock(rows: list[tuple[int, int, str]], labels: str) -> list[str]:
    touched = [p for _, _, p in rows if p in LOCK_PATHS]
    if not touched:
        return []
    have = {label.strip() for label in labels.split(",") if label.strip()}
    if UNLOCK_LABEL not in have:
        return [f"잠금 파일 변경({', '.join(touched)}) — PR 라벨 '{UNLOCK_LABEL}' 없음"]
    return []


def main() -> int:
    env = os.environ
    cwd = os.getcwd()
    try:
        base = resolve_base(env)
        rows = diff_numstat(base, cwd)
        authors = commit_author_emails(base, cwd)
    except RuntimeError as exc:
        print(f"[guard] 실행 오류: {exc}", file=sys.stderr)
        return 1
    reasons = [
        *guard_size(rows),
        *guard_tests_not_weakened(rows),
        *guard_b_only(rows, authors, env.get("B_EMAIL", "")),
        *guard_unlock(rows, env.get("PR_LABELS", "")),
    ]
    if reasons:
        for reason in reasons:
            print(f"[guard] 실패: {reason}")
        return 1
    lines = sum(added + deleted for added, deleted, _ in rows)
    print(f"[guard] 통과: diff {lines}줄 / {len(rows)}개 파일 — 상한 내")
    return 0


if __name__ == "__main__":
    sys.exit(main())
