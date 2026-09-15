import asyncio
import re
import time

import pytest

import app.providers.mock as mock_module
from app.providers.errors import (
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderInvalidResponseError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.mock import MockProvider
from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse


def _request(model: str = "mock-v1") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[ChatMessage(role="user", content="hello")],
    )


def test_normal_mode_returns_unified_response_with_injected_request_id() -> None:
    async def run() -> ChatResponse:
        provider = MockProvider(request_id_factory=lambda: "req_injected")
        return await provider.chat(_request("requested-model"))

    response = asyncio.run(run())

    assert isinstance(response, ChatResponse)
    assert response.provider == "mock"
    assert response.model == "requested-model"
    assert response.content == "mock response"
    assert response.request_id == "req_injected"
    assert response.latency_ms >= 0
    assert response.usage.model_dump() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_default_request_id_has_expected_prefix() -> None:
    async def run() -> ChatResponse:
        return await MockProvider().chat(_request())

    response = asyncio.run(run())

    assert re.fullmatch(r"req_[0-9a-f]{32}", response.request_id)


def test_unknown_mode_is_rejected_during_construction() -> None:
    with pytest.raises(ProviderConfigurationError):
        MockProvider(mode="typo")


def test_negative_slow_delay_is_rejected_during_construction() -> None:
    with pytest.raises(ProviderConfigurationError):
        MockProvider(slow_delay_seconds=-0.001)


def test_timeout_mode_raises_provider_timeout_error() -> None:
    async def run() -> None:
        with pytest.raises(ProviderTimeoutError):
            await MockProvider(mode="timeout").chat(_request())

    asyncio.run(run())


def test_rate_limit_mode_raises_provider_rate_limit_error() -> None:
    async def run() -> None:
        with pytest.raises(ProviderRateLimitError):
            await MockProvider(mode="429").chat(_request())

    asyncio.run(run())


def test_server_error_mode_raises_provider_server_error() -> None:
    async def run() -> None:
        with pytest.raises(ProviderServerError):
            await MockProvider(mode="500").chat(_request())

    asyncio.run(run())


def test_connection_error_mode_raises_provider_connection_error() -> None:
    async def run() -> None:
        with pytest.raises(ProviderConnectionError):
            await MockProvider(mode="connection_error").chat(_request())

    asyncio.run(run())


def test_invalid_response_mode_raises_provider_invalid_response_error() -> None:
    async def run() -> None:
        with pytest.raises(ProviderInvalidResponseError):
            await MockProvider(mode="invalid_response").chat(_request())

    asyncio.run(run())


def test_slow_response_mode_waits_for_configured_delay_and_returns_success() -> None:
    async def run() -> tuple[ChatResponse, float]:
        provider = MockProvider(
            mode="slow_response",
            slow_delay_seconds=0.01,
            request_id_factory=lambda: "req_slow",
        )
        started = time.perf_counter()
        response = await provider.chat(_request("slow-model"))
        return response, time.perf_counter() - started

    response, elapsed = asyncio.run(run())

    assert elapsed >= 0.008
    assert isinstance(response, ChatResponse)
    assert response.provider == "mock"
    assert response.model == "slow-model"
    assert response.content == "mock response"
    assert response.request_id == "req_slow"
    assert response.latency_ms >= 8
    assert response.usage.model_dump() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_unhandled_validated_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mock_module,
        "get_args",
        lambda _: (
            "normal",
            "timeout",
            "429",
            "500",
            "connection_error",
            "invalid_response",
            "slow_response",
            "future_mode",
        ),
    )

    async def run() -> None:
        with pytest.raises(ProviderConfigurationError):
            await mock_module.MockProvider(mode="future_mode").chat(_request())

    asyncio.run(run())
