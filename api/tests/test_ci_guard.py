"""scripts/ci_guard.py 단위 테스트 — /tmp synthetic git 리포로 diff 시나리오를 구성한다.

guard 잡은 PR base diff가 필요하므로 로컬 재현 대상이 아니고(계획 M16),
이 유닛 4케이스가 가드 판정 로직의 로컬 커버리지다. B_EMAIL은 환경변수로 주입한다(A5).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_SCRIPT = REPO_ROOT / "scripts" / "ci_guard.py"

B_EMAIL = "b@org.example"
OTHER_EMAIL = "stranger@example.com"


def _git(repo: Path, *args: str, email: str = "setup@local") -> None:
    subprocess.run(
        ["git", "-c", f"user.email={email}", "-c", "user.name=tester", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed")
    return repo


def _run_guard(repo: Path, *, labels: str = "") -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GITHUB_BASE_REF": "base", "B_EMAIL": B_EMAIL, "PR_LABELS": labels}
    env.pop("BASE_REF", None)
    return subprocess.run(
        [sys.executable, str(GUARD_SCRIPT)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_oversize_diff_fails(tmp_path: Path) -> None:
    # Given: base에서 401줄을 추가한 PR (상한 400줄)
    repo = _init_repo(tmp_path)
    _git(repo, "branch", "base")
    (repo / "generated.txt").write_text(
        "\n".join(f"line {i}" for i in range(401)) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "big")
    # When: 가드 실행
    proc = _run_guard(repo)
    # Then: 초과 판정으로 실패
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "400" in proc.stdout


def test_api_tests_deletion_outweighs_addition_fails(tmp_path: Path) -> None:
    # Given: api/tests/test_x.py 10줄을 base로 삼고, 9줄 삭제 1줄 추가로 완화한 PR
    repo = _init_repo(tmp_path)
    tests_dir = repo / "api" / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_x.py").write_text(
        "\n".join(f"def case_{i}(): pass" for i in range(10)) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed tests")
    _git(repo, "branch", "base")
    (tests_dir / "test_x.py").write_text("def case_0(): pass\n# kept\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "trim")
    # When: 가드 실행
    proc = _run_guard(repo)
    # Then: 테스트 완화 판정으로 실패
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "api/tests" in proc.stdout


def test_rules_change_by_non_b_author_fails(tmp_path: Path) -> None:
    # Given: rules/**를 B가 아닌 author 이메일로 변경한 커밋
    repo = _init_repo(tmp_path)
    _git(repo, "branch", "base")
    rules_dir = repo / "rules"
    rules_dir.mkdir()
    (rules_dir / "new-rule.yaml").write_text("rules: []\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add rule", email=OTHER_EMAIL)
    # When: 가드 실행
    proc = _run_guard(repo)
    # Then: B 아님 판정으로 실패
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert OTHER_EMAIL in proc.stdout


def test_pipeline_change_with_unlock_label_passes(tmp_path: Path) -> None:
    # Given: pipeline.py 변경 + unlock-approved 라벨
    repo = _init_repo(tmp_path)
    _git(repo, "branch", "base")
    worker_dir = repo / "api" / "worker"
    worker_dir.mkdir(parents=True)
    (worker_dir / "pipeline.py").write_text("def run(): ...\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "touch pipeline", email=B_EMAIL)
    # When: unlock-approved 라벨과 함께 가드 실행
    proc = _run_guard(repo, labels="unlock-approved")
    # Then: 통과
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[guard] 통과" in proc.stdout
