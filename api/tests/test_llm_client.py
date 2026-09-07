"""SPEC §7.1 벽시계 예산 — 진행 중 호출도 데드라인에 잘린다. DB·네트워크 없음."""

import time as time_mod

from worker.llm import client as llm_client


class _SlowCompletions:
    @staticmethod
    def create(**kwargs):
        time_mod.sleep(5)


class _SlowChat:
    completions = _SlowCompletions()


class _SlowClient:
    chat = _SlowChat()


def _client_with_slow_backend() -> llm_client.LLMClient:
    cli = llm_client.LLMClient.__new__(llm_client.LLMClient)
    cli.model = "m"
    cli.model_fallback = ""
    cli.base_url = llm_client.DEFAULT_BASE_URL
    cli._client = _SlowClient()
    return cli


def test_chat_json_enforces_wall_budget():
    cli = _client_with_slow_backend()
    budget = llm_client.Budget(deadline=time_mod.monotonic() + 0.3)

    started = time_mod.monotonic()
    result = cli.chat_json(budget, "sys", "user", "s", {"type": "object", "properties": {}}, 10)
    elapsed = time_mod.monotonic() - started

    assert result is None
    assert elapsed < 4, f"budget not enforced: {elapsed:.1f}s"
