import asyncio
import time
from collections.abc import Callable
from typing import Literal, get_args
from uuid import uuid4

from app.providers.base import BaseProvider
from app.providers.errors import (
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.schemas import ChatRequest, ChatResponse, TokenUsage

MockMode = Literal[
    "normal",
    "timeout",
    "429",
    "500",
    "connection_error",
    "invalid_response",
    "slow_response",
]


def default_request_id() -> str:
    return f"req_{uuid4().hex}"


class MockProvider(BaseProvider):
    _immediate_failures: dict[str, type[ProviderError]] = {
        "timeout": ProviderTimeoutError,
        "429": ProviderRateLimitError,
        "500": ProviderServerError,
        "connection_error": ProviderConnectionError,
        "invalid_response": ProviderInvalidResponseError,
    }

    def __init__(
        self,
        mode: MockMode = "normal",
        slow_delay_seconds: float = 0.01,
        request_id_factory: Callable[[], str] = default_request_id,
    ) -> None:
        if mode not in get_args(MockMode) or slow_delay_seconds < 0:
            raise ProviderConfigurationError(provider="mock")
        self.mode = mode
        self.slow_delay_seconds = slow_delay_seconds
        self.request_id_factory = request_id_factory

    async def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()

        if self.mode in self._immediate_failures:
            error_type = self._immediate_failures[self.mode]
            status_code = {"429": 429, "500": 500}.get(self.mode)
            # 使用确定性模式复现故障，避免随机失败导致测试不稳定。
            raise error_type(provider="mock", status_code=status_code)

        if self.mode == "normal":
            return self._success_response(request, started)

        if self.mode == "slow_response":
            await asyncio.sleep(self.slow_delay_seconds)
            return self._success_response(request, started)

        raise ProviderConfigurationError(provider="mock")

    def _success_response(
        self, request: ChatRequest, started: float
    ) -> ChatResponse:
        return ChatResponse(
            request_id=self.request_id_factory(),
            provider="mock",
            model=request.model,
            content="mock response",
            latency_ms=(time.perf_counter() - started) * 1000,
            usage=TokenUsage(),
        )
