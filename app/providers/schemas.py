from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """屏蔽供应商消息格式差异的统一消息契约。"""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """业务层提交给任意供应商的统一请求。"""

    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)


class TokenUsage(BaseModel):
    """统一供应商之间可能缺失的 token 用量字段。"""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ChatResponse(BaseModel):
    """业务层可稳定消费的统一响应，不暴露供应商原始载荷。"""

    request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    content: str = Field(min_length=1)
    latency_ms: float = Field(ge=0)
    usage: TokenUsage
