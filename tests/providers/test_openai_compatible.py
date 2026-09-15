import asyncio

import httpx
import pytest

from app.providers.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderConnectionError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
    ProviderTimeoutError,
)
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse


def _request() -> ChatRequest:
    return ChatRequest(
        model="requested-model",
        messages=[
            ChatMessage(role="system", content="Be brief"),
            ChatMessage(role="user", content="hello"),
        ],
    )


def test_chat_posts_openai_payload_and_maps_complete_response() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-123",
                "model": "served-model",
                "choices": [{"message": {"content": "hello back"}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        )

    async def run() -> ChatResponse:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1/",
                api_key="test-secret-key",
                provider_name="example-provider",
                client=client,
            )
            return await provider.chat(_request())

    response = asyncio.run(run())

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert str(captured_request.url) == "https://provider.example/v1/chat/completions"
    assert captured_request.headers["Authorization"] == "Bearer test-secret-key"
    assert captured_request.read() == (
        b'{"model":"requested-model","messages":'
        b'[{"role":"system","content":"Be brief"},'
        b'{"role":"user","content":"hello"}]}'
    )
    assert response == ChatResponse(
        request_id="chatcmpl-123",
        provider="example-provider",
        model="served-model",
        content="hello back",
        latency_ms=response.latency_ms,
        usage={
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    )
    assert response.latency_ms >= 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": ""},
        {"base_url": "   "},
        {"api_key": ""},
        {"api_key": "   "},
        {"provider_name": ""},
        {"provider_name": "   "},
        {"timeout_seconds": 0},
        {"timeout_seconds": -0.1},
    ],
)
def test_constructor_rejects_invalid_configuration(
    overrides: dict[str, object],
) -> None:
    options: dict[str, object] = {
        "base_url": "https://provider.example/v1",
        "api_key": "test-secret-key",
        "provider_name": "safe-provider",
        "timeout_seconds": 5.0,
    }
    options.update(overrides)

    with pytest.raises(ProviderConfigurationError) as caught:
        OpenAICompatibleProvider(**options)

    assert "test-secret-key" not in str(caught.value)


def _assert_configuration_error_is_safe(
    error: ProviderConfigurationError,
    api_key: str,
) -> None:
    assert error.provider == "safe-provider"
    assert error.status_code is None
    exposed_surfaces = (
        str(error),
        repr(error),
        repr(error.args),
        repr(vars(error)),
    )
    assert all(api_key not in surface for surface in exposed_surfaces)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://provider.example:bad",
        "provider.example/v1",
        "ftp://provider.example/v1",
    ],
)
def test_constructor_rejects_invalid_http_url_without_leaking_key(
    base_url: str,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async def run() -> ProviderConfigurationError:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderConfigurationError) as caught:
                OpenAICompatibleProvider(
                    base_url=base_url,
                    api_key="test-url-secret-key",
                    provider_name="safe-provider",
                    client=client,
                )
            return caught.value
        finally:
            await client.aclose()

    error = asyncio.run(run())

    _assert_configuration_error_is_safe(error, "test-url-secret-key")


@pytest.mark.parametrize(
    "api_key",
    [
        "sk-unicode-密钥",
        "sk-line\r\nInjected: yes",
    ],
)
def test_constructor_rejects_unsafe_authorization_key(api_key: str) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async def run() -> ProviderConfigurationError:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderConfigurationError) as caught:
                OpenAICompatibleProvider(
                    base_url="https://provider.example/v1",
                    api_key=api_key,
                    provider_name="safe-provider",
                    client=client,
                )
            return caught.value
        finally:
            await client.aclose()

    error = asyncio.run(run())

    _assert_configuration_error_is_safe(error, api_key)


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (400, ProviderRequestError),
        (418, ProviderRequestError),
        (500, ProviderServerError),
        (503, ProviderServerError),
    ],
)
def test_chat_maps_http_status_to_safe_provider_error(
    status_code: int,
    error_type: type[Exception],
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="sensitive-response-body")

    async def run() -> Exception:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1",
                api_key="test-status-secret-key",
                provider_name="safe-provider",
                client=client,
            )
            with pytest.raises(error_type) as caught:
                await provider.chat(_request())
            return caught.value
        finally:
            await client.aclose()

    error = asyncio.run(run())

    assert getattr(error, "provider") == "safe-provider"
    assert getattr(error, "status_code") == status_code
    assert "test-status-secret-key" not in str(error)
    assert "Authorization" not in str(error)
    assert "sensitive-response-body" not in str(error)
    assert not isinstance(error, httpx.HTTPStatusError)


@pytest.mark.parametrize(
    ("httpx_error_type", "provider_error_type"),
    [
        (httpx.ReadTimeout, ProviderTimeoutError),
        (httpx.WriteTimeout, ProviderTimeoutError),
        (httpx.ConnectError, ProviderConnectionError),
        (httpx.ReadError, ProviderConnectionError),
        (httpx.RemoteProtocolError, ProviderConnectionError),
    ],
)
def test_chat_maps_transport_failures_to_safe_provider_error(
    httpx_error_type: type[httpx.RequestError],
    provider_error_type: type[Exception],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx_error_type("transport-sensitive-detail", request=request)

    async def run() -> Exception:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1",
                api_key="test-transport-secret-key",
                provider_name="safe-provider",
                client=client,
            )
            with pytest.raises(provider_error_type) as caught:
                await provider.chat(_request())
            return caught.value
        finally:
            await client.aclose()

    error = asyncio.run(run())

    assert getattr(error, "provider") == "safe-provider"
    assert getattr(error, "status_code") is None
    assert "test-transport-secret-key" not in str(error)
    assert "transport-sensitive-detail" not in str(error)
    assert not isinstance(error, httpx.RequestError)


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"content": b"sensitive-invalid-json"}, id="invalid-json"),
        pytest.param(
            {"json": {"id": "req-1", "model": "model-1", "choices": []}},
            id="empty-choices",
        ),
        pytest.param(
            {"json": {"id": "req-1", "model": "model-1", "choices": [{}]}},
            id="missing-message",
        ),
        pytest.param(
            {
                "json": {
                    "id": "req-1",
                    "model": "model-1",
                    "choices": [{"message": {}}],
                }
            },
            id="missing-content",
        ),
        pytest.param(
            {
                "json": {
                    "id": 123,
                    "model": "model-1",
                    "choices": [{"message": {"content": "hello"}}],
                }
            },
            id="wrong-id-type",
        ),
        pytest.param(
            {
                "json": {
                    "id": "req-1",
                    "model": 123,
                    "choices": [{"message": {"content": "hello"}}],
                }
            },
            id="wrong-model-type",
        ),
        pytest.param(
            {
                "json": {
                    "id": "req-1",
                    "model": "model-1",
                    "choices": [{"message": {"content": 123}}],
                }
            },
            id="wrong-content-type",
        ),
        pytest.param(
            {
                "json": {
                    "id": "req-1",
                    "model": "model-1",
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": "1"},
                }
            },
            id="wrong-usage-type",
        ),
    ],
)
def test_chat_translates_malformed_success_payload(
    response_kwargs: dict[str, object],
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, **response_kwargs)

    async def run() -> ProviderInvalidResponseError:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1",
                api_key="test-response-secret-key",
                provider_name="safe-provider",
                client=client,
            )
            with pytest.raises(ProviderInvalidResponseError) as caught:
                await provider.chat(_request())
            return caught.value
        finally:
            await client.aclose()

    error = asyncio.run(run())

    assert error.provider == "safe-provider"
    assert error.status_code == 200
    assert "test-response-secret-key" not in str(error)
    assert "sensitive-invalid-json" not in str(error)


@pytest.mark.parametrize(
    ("payload", "expected_usage"),
    [
        (
            {
                "id": "req-1",
                "model": "model-1",
                "choices": [{"message": {"content": "hello"}}],
            },
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        ),
        (
            {
                "id": "req-1",
                "model": "model-1",
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 3},
            },
            {"prompt_tokens": 3, "completion_tokens": 0, "total_tokens": 0},
        ),
    ],
)
def test_chat_defaults_missing_usage_fields_to_zero(
    payload: dict[str, object],
    expected_usage: dict[str, int],
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def run() -> ChatResponse:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1",
                api_key="test-secret-key",
                client=client,
            )
            return await provider.chat(_request())
        finally:
            await client.aclose()

    response = asyncio.run(run())

    assert response.usage.model_dump() == expected_usage


def test_aclose_keeps_injected_client_open() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    async def run() -> bool:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            provider = OpenAICompatibleProvider(
                base_url="https://provider.example/v1",
                api_key="test-secret-key",
                client=client,
            )
            await provider.aclose()
            return client.is_closed
        finally:
            await client.aclose()

    assert asyncio.run(run()) is False


def test_aclose_closes_internally_created_client() -> None:
    async def run() -> bool:
        provider = OpenAICompatibleProvider(
            base_url="https://provider.example/v1",
            api_key="test-secret-key",
        )
        owned_client = provider._client
        await provider.aclose()
        return owned_client.is_closed

    assert asyncio.run(run()) is True
