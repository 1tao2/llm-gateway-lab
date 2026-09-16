import asyncio
import json

import httpx
import pytest

from app.providers.errors import ProviderConfigurationError
from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse
from app.providers.zhipu import ZhipuProvider


def _request() -> ChatRequest:
    return ChatRequest(
        model="glm-4-flash",
        messages=[ChatMessage(role="user", content="你好")],
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"api_key": ""},
        {"api_key": "   "},
        {"base_url": ""},
        {"base_url": "   "},
    ],
)
def test_constructor_rejects_empty_required_configuration(
    overrides: dict[str, str],
) -> None:
    options = {
        "api_key": "test-zhipu-key",
        "base_url": "https://zhipu.example/api/paas/v4",
    }
    options.update(overrides)

    with pytest.raises(ProviderConfigurationError) as caught:
        ZhipuProvider(**options)

    assert caught.value.provider == "zhipu"
    assert "test-zhipu-key" not in str(caught.value)


def test_chat_uses_compatible_protocol_and_marks_response_as_zhipu() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "id": "zhipu-request-1",
                "model": "glm-4-flash",
                "choices": [{"message": {"content": "智谱响应"}}],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                },
            },
        )

    async def run() -> ChatResponse:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = ZhipuProvider(
                api_key="test-zhipu-key",
                base_url="https://zhipu.example/api/paas/v4/",
                client=client,
            )
            return await provider.chat(_request())

    response = asyncio.run(run())

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert str(captured_request.url) == (
        "https://zhipu.example/api/paas/v4/chat/completions"
    )
    assert captured_request.headers["Authorization"] == "Bearer test-zhipu-key"
    assert json.loads(captured_request.read()) == {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": "你好"}],
    }
    assert response == ChatResponse(
        request_id="zhipu-request-1",
        provider="zhipu",
        model="glm-4-flash",
        content="智谱响应",
        latency_ms=response.latency_ms,
        usage={
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "total_tokens": 5,
        },
    )


def test_aclose_keeps_injected_client_open() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async def run() -> bool:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = ZhipuProvider(api_key="test-zhipu-key", client=client)
            await provider.aclose()
            return client.is_closed
        finally:
            await client.aclose()

    assert asyncio.run(run()) is False


def test_aclose_closes_internally_created_client() -> None:
    async def run() -> bool:
        provider = ZhipuProvider(api_key="test-zhipu-key")
        owned_client = provider._provider._client
        await provider.aclose()
        return owned_client.is_closed

    assert asyncio.run(run()) is True
