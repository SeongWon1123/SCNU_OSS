"""Shared test fixtures — real Postgres via deps.engine (compose db service).

app/sqlalchemy/openai are imported lazily inside the fixtures: the CI `rules` job
(ci.yml) installs only semgrep+pytest+pyyaml and runs test_semgrep_rules.py, which
needs none of them. Without the app stack no DB/LLM test can even be imported, so
skipping these fixtures there hides nothing; with it installed they run unchanged.
"""

from importlib.util import find_spec

import pytest

_APP_STACK = find_spec("sqlalchemy") is not None and find_spec("openai") is not None


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> None:
    if not _APP_STACK:
        return
    from app import deps
    from app.models import Base

    Base.metadata.create_all(deps.engine)


@pytest.fixture(autouse=True)
def _no_live_llm(monkeypatch):
    """PROMPTS.md:86 — .env에 실제 키이 있어도 테스트는 LLM 네트워크를 치지 않는다.

    LLM 경로를 검증하는 테스트(test_pipeline_fake의 Phase 4 블록)는 테스트 본문에서
    같은 대상을 자체 fake로 다시 setattr해 이 경비를 덮어쓴다(본문이 나중에 적용됨).
    """
    if not _APP_STACK:
        return
    from worker.llm import client as llm_client

    class _ForbiddenOpenAI:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("테스트에서 실제 LLM 호출 금지 — OpenAI 심을 fake로 대체할 것")

    monkeypatch.setattr(llm_client, "OpenAI", _ForbiddenOpenAI)


@pytest.fixture(autouse=True)
def _clean_tables() -> None:
    if not _APP_STACK:
        yield
        return
    from sqlalchemy import text

    from app import deps

    # Truncate BEFORE each test (setup time): deps.engine is guaranteed to be the
    # real Postgres engine here, while per-test teardown order with test_health's
    # monkeypatched sqlite engine is not something to rely on.
    with deps.engine.begin() as conn:
        conn.execute(text("TRUNCATE findings, scans, rate_limit_hits RESTART IDENTITY CASCADE"))
    yield
