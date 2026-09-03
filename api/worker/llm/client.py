"""LLM 클라이언트 — SPEC.md §7.1: OpenAI SDK, 기동 모델 확인, 스캔당 예산.

- OpenAI(timeout=20, max_retries=1). 모델은 OPENAI_MODEL(없으면 비활성).
- base_url은 OPENAI_BASE_URL env(OpenRouter 경유 — 사용자 결정 2026-09-03).
  SDK가 이 env를 네이티브로 읽지만, 공식 엔드포인트 기본값과 함께 코드에 명시한다.
- ⑥ 편차(SPEC.md:244 "실패 시 LLM_ENABLED=false"): models.retrieve 1회가
  404/오류여도 models.list 재확인을 먼저 한다 — OpenRouter는 retrieve를 404로
  답할 수 있어 그것만으로 LLM을 끄지 않는다. list까지 실패하면 비활성.
- 스캔당 예산: 벽시계 45초 · 호출 최대 3회 · 입력 합 20k 토큰(근사). 초과·429·
  파싱 실패 시 호출은 None을 돌려주고 상위 단계가 status='skipped'로 마친다.
"""

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass

from openai import BadRequestError, OpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
CALL_TIMEOUT_SECONDS = 20
MAX_RETRIES = 1
WALL_BUDGET_SECONDS = 45
MAX_CALLS = 3
MAX_INPUT_TOKENS = 20_000
_TOKEN_CHARS = 3  # 근사: 한글·영문 혼합 1토큰 ≈ 3자
REASONING_HEADROOM_TOKENS = 4000  # 추론 모델의 reasoning 소비분 — content 상한은 유지

ProbeKey = tuple[str, str, str]


def est_tokens(text: str) -> int:
    return max(1, (len(text) + _TOKEN_CHARS - 1) // _TOKEN_CHARS)


@dataclass
class Budget:
    """스캔당 LLM 예산 — explain→policy 단계가 같은 인스턴스를 공유한다."""

    deadline: float  # time.monotonic() 기준
    calls: int = 0
    input_tokens: int = 0
    max_calls: int = MAX_CALLS
    max_input_tokens: int = MAX_INPUT_TOKENS

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline

    def exhausted(self) -> bool:
        return self.calls >= self.max_calls

    def admit(self, prompt_tokens: int) -> bool:
        return not (
            self.expired()
            or self.exhausted()
            or self.input_tokens + prompt_tokens > self.max_input_tokens
        )


_BUDGETS: dict[str, Budget] = {}
_PROBE_CACHE: dict[ProbeKey, bool] = {}


def budget_for(scan_id: str) -> Budget:
    budget = _BUDGETS.get(scan_id)
    if budget is None:
        budget = Budget(deadline=time.monotonic() + WALL_BUDGET_SECONDS)
        _BUDGETS[scan_id] = budget
    return budget


def drop_budget(scan_id: str) -> None:
    _BUDGETS.pop(scan_id, None)


def startup_probe(settings: Settings) -> bool:
    """worker 기동 시 1회(§7.1). 결과는 (모델·base_url·키 지문) 캐시로 재사용."""
    return LLMClient(settings).probe()


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.openai_model
        self.model_fallback = settings.openai_model_fallback
        self.base_url = os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL
        self._client: OpenAI | None = None
        if settings.openai_api_key and self.model:
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=self.base_url,
                timeout=CALL_TIMEOUT_SECONDS,
                max_retries=MAX_RETRIES,
            )

    def probe(self) -> bool:
        if self._client is None:
            return False
        key_fp = hashlib.sha256(self._client.api_key.encode()).hexdigest()[:12]
        cache_key: ProbeKey = (self.model, self.base_url, key_fp)
        if cache_key not in _PROBE_CACHE:
            _PROBE_CACHE[cache_key] = self._probe_uncached()
        return _PROBE_CACHE[cache_key]

    def _probe_uncached(self) -> bool:
        assert self._client is not None
        try:
            self._client.models.retrieve(self.model)
            return True
        except Exception as exc:  # noqa: BLE001 — 404·401·네트워크 모두 재확인 대상
            logger.warning("models.retrieve 실패(%s) — models.list로 재확인", type(exc).__name__)
        try:
            self._client.models.list()
            return True
        except Exception:  # noqa: BLE001 — 명명된 실패 경계: 비활성으로 진행(§7.1)
            return False

    def chat_json(
        self,
        budget: Budget,
        system: str,
        user: str,
        schema_name: str,
        schema: dict,
        max_output_tokens: int,
    ) -> dict | None:
        """예산 안에서 JSON 응답 1회 요청. 실패·예산 초과 시 None(스캔은 계속)."""
        if self._client is None:
            return None
        prompt_tokens = est_tokens(system) + est_tokens(user)
        if not budget.admit(prompt_tokens):
            return None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        formats = [
            {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            {"type": "json_object"},  # ⑥: json_schema strict 미지원 공급자 폴백
        ]
        models = [self.model]
        if self.model_fallback:
            models.append(self.model_fallback)
        for model in models:
            for fmt in formats:
                if budget.expired() or budget.exhausted():
                    return None
                budget.calls += 1
                budget.input_tokens += prompt_tokens
                # ⑥ OpenRouter 추론 모델 호환: reasoning 토큰이 max_tokens를 먼저
                # 소진하면 content가 빈 채로 끝난다 — content 상한(§7.2 4k)은 그대로
                # 두고 추론 헤드룸만 더하고, reasoning은 응답에서 제외한다.
                # 공식 엔드포인트에는 이 파라미터를 보내지 않는다.
                extra_body: dict | None = None
                max_tokens = max_output_tokens
                if self.base_url != DEFAULT_BASE_URL:
                    extra_body = {"reasoning": {"effort": "low", "exclude": True}}
                    max_tokens = max_output_tokens + REASONING_HEADROOM_TOKENS
                try:
                    response = self._client.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_format=fmt,
                        max_tokens=max_tokens,
                        extra_body=extra_body,
                    )
                    return json.loads(response.choices[0].message.content)
                except BadRequestError:
                    continue  # json_schema 미지원 → json_object → fallback 모델
                except Exception as exc:  # noqa: BLE001 — 429·네트워크·파싱 모두 폴백 대상
                    logger.warning("LLM 호출 실패(%s) — 스캔은 skipped로 계속", type(exc).__name__)
                    return None
        return None
