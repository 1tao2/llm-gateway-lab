import math
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.providers.base import BaseProvider
from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.schemas import ChatRequest, ChatResponse, TokenUsage


class _ResponseMessage(BaseModel):
    model_config = ConfigDict(strict=True)

    content: str


class _ResponseChoice(BaseModel):
    model_config = ConfigDict(strict=True)

    message: _ResponseMessage


class _ResponseUsage(BaseModel):
    model_config = ConfigDict(strict=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class _OpenAIResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    choices: list[_ResponseChoice] = Field(min_length=1)
    usage: _ResponseUsage = Field(default_factory=_ResponseUsage)


class OpenAICompatibleProvider(BaseProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        provider_name: str = "openai-compatible",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        safe_provider = (
            provider_name.strip()
            if isinstance(provider_name, str) and provider_name.strip()
            else "openai-compatible"
        )
        valid_timeout = (
            isinstance(timeout_seconds, (int, float))
            and not isinstance(timeout_seconds, bool)
            and math.isfinite(timeout_seconds)
            and timeout_seconds > 0
        )
        if (
            not isinstance(base_url, str)
            or not base_url.strip()
            or not isinstance(api_key, str)
            or not api_key.strip()
            or not isinstance(provider_name, str)
            or not provider_name.strip()
            or not valid_timeout
        ):
            raise ProviderConfigurationError(provider=safe_provider)

        normalized_api_key = api_key.strip()
        # 构造阶段验证 HTTPX 边界，避免原生异常携带密钥越过 Provider。
        try:
            parsed_base_url = httpx.URL(base_url.strip())
            f"Bearer {normalized_api_key}".encode("ascii")
        except (httpx.InvalidURL, UnicodeError, ValueError):
            parsed_base_url = None
        # 离开 except 后再抛出，避免 __context__ 保留 URL 或密钥。
        if (
            parsed_base_url is None
            or parsed_base_url.scheme not in ("http", "https")
            or not parsed_base_url.host
            # 仅允许配置的 Bearer 认证，不接收 URL 内嵌凭据。
            or parsed_base_url.userinfo
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in api_key
            )
        ):
            raise ProviderConfigurationError(provider=safe_provider)

        self._base_url = str(parsed_base_url).rstrip("/")
        self._api_key = normalized_api_key
        self._provider_name = provider_name.strip()
        self._timeout_seconds = float(timeout_seconds)
        # 仅关闭本实例创建的客户端；注入客户端的生命周期由调用方负责。
        self._owns_client = client is None
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(timeout=self._timeout_seconds)
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        transport_error_type: type[ProviderError] | None = None
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                # 禁用注入客户端的默认认证，避免覆盖 Provider 的 Bearer 头。
                auth=None,
                json={
                    "model": request.model,
                    "messages": [message.model_dump() for message in request.messages],
                },
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            transport_error_type = ProviderTimeoutError
        except httpx.RequestError:
            transport_error_type = ProviderConnectionError
        except httpx.HTTPStatusError as error:
            # 注入客户端的响应 hook 可能提前检查状态，仍复用统一映射。
            response = error.response
        # 只保存分类；离开 except 后抛出，彻底断开含请求凭据的异常链。
        if transport_error_type is not None:
            raise transport_error_type(provider=self._provider_name)
        self._raise_for_status(response.status_code)
        try:
            payload = _OpenAIResponse.model_validate(response.json())

            # 只在协议边界映射字段，避免业务层依赖供应商原始响应。
            return ChatResponse(
                request_id=payload.id,
                provider=self._provider_name,
                model=payload.model,
                content=payload.choices[0].message.content,
                latency_ms=(time.perf_counter() - started) * 1000,
                usage=TokenUsage(**payload.usage.model_dump()),
            )
        except (ValueError, KeyError, TypeError, IndexError):
            pass
        # JSON/Pydantic 异常可能包含完整响应正文，不能成为安全异常的上下文。
        raise ProviderInvalidResponseError(
            provider=self._provider_name,
            status_code=response.status_code,
        )

    def _raise_for_status(self, status_code: int) -> None:
        # 区分认证、限流、请求与服务端错误，供后续可靠性策略判断是否重试。
        if status_code in (401, 403):
            error_type = ProviderAuthenticationError
        elif status_code == 429:
            error_type = ProviderRateLimitError
        # 重定向同样表示请求未完成，避免响应 hook 抛错后继续解析未读响应。
        elif 300 <= status_code < 500:
            error_type = ProviderRequestError
        elif status_code >= 500:
            error_type = ProviderServerError
        else:
            return
        raise error_type(provider=self._provider_name, status_code=status_code)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
