from abc import ABC, abstractmethod

from app.providers.schemas import ChatRequest, ChatResponse


class BaseProvider(ABC):
    """统一供应商边界，业务层只依赖规范化请求、响应和异常。"""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise NotImplementedError
