import asyncio

import httpx

from app.providers.base import BaseProvider
from app.providers.mock import MockProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.schemas import ChatMessage, ChatRequest
from app.providers.zhipu import ZhipuProvider


async def get_content(provider: BaseProvider, request: ChatRequest) -> str:
    """业务代码只依赖统一 Provider 契约。"""
    response = await provider.chat(request)
    return response.content


def _request() -> ChatRequest:
    return ChatRequest(
        model="contract-model",
        messages=[ChatMessage(role="user", content="hello")],
    )


def _compatible_response(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "contract-request",
            "model": "contract-model",
            "choices": [{"message": {"content": "mock response"}}],
        },
    )


def test_business_function_accepts_all_provider_implementations() -> None:
    async def run() -> list[str]:
        transport = httpx.MockTransport(_compatible_response)
        async with httpx.AsyncClient(transport=transport) as client:
            providers: list[BaseProvider] = [
                MockProvider(request_id_factory=lambda: "contract-mock"),
                OpenAICompatibleProvider(
                    base_url="https://compatible.example/v1",
                    api_key="test-compatible-key",
                    client=client,
                ),
                ZhipuProvider(
                    api_key="test-zhipu-key",
                    base_url="https://zhipu.example/api/paas/v4",
                    client=client,
                ),
            ]
            return [await get_content(provider, _request()) for provider in providers]

    assert asyncio.run(run()) == [
        "mock response",
        "mock response",
        "mock response",
    ]
