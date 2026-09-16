import httpx

from app.providers.base import BaseProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.schemas import ChatRequest, ChatResponse


class ZhipuProvider(BaseProvider):
    """组合兼容实现，避免为智谱维护第二套 HTTP 与异常处理栈。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider = OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            provider_name="zhipu",
            timeout_seconds=timeout_seconds,
            client=client,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return await self._provider.chat(request)

    async def aclose(self) -> None:
        await self._provider.aclose()
