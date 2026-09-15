import pytest
from pydantic import ValidationError

from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse, TokenUsage


def test_chat_response_preserves_the_unified_contract() -> None:
    response = ChatResponse(
        request_id="req_1",
        provider="mock",
        model="mock-v1",
        content="hello",
        latency_ms=1.5,
        usage=TokenUsage(
            prompt_tokens=2,
            completion_tokens=3,
            total_tokens=5,
        ),
    )

    assert response.model_dump() == {
        "request_id": "req_1",
        "provider": "mock",
        "model": "mock-v1",
        "content": "hello",
        "latency_ms": 1.5,
        "usage": {
            "prompt_tokens": 2,
            "completion_tokens": 3,
            "total_tokens": 5,
        },
    }


@pytest.mark.parametrize("field", ["request_id", "provider", "model", "content"])
def test_chat_response_rejects_empty_required_strings(field: str) -> None:
    payload = {
        "request_id": "req_1",
        "provider": "mock",
        "model": "mock-v1",
        "content": "hello",
        "latency_ms": 1.5,
        "usage": {},
    }
    payload[field] = ""

    with pytest.raises(ValidationError):
        ChatResponse.model_validate(payload)


def test_chat_response_rejects_negative_latency() -> None:
    with pytest.raises(ValidationError):
        ChatResponse(
            request_id="req_1",
            provider="mock",
            model="mock-v1",
            content="hello",
            latency_ms=-0.1,
            usage=TokenUsage(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "", "messages": [{"role": "user", "content": "hello"}]},
        {"model": "mock-v1", "messages": []},
        {
            "model": "mock-v1",
            "messages": [{"role": "tool", "content": "hello"}],
        },
        {"model": "mock-v1", "messages": [{"role": "user", "content": ""}]},
    ],
    ids=["empty-model", "empty-messages", "tool-role", "empty-content"],
)
def test_chat_request_rejects_invalid_boundary_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(payload)


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1},
        {"completion_tokens": -1},
        {"total_tokens": -1},
    ],
    ids=["prompt", "completion", "total"],
)
def test_token_usage_rejects_negative_counts(usage: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        TokenUsage(**usage)


def test_token_usage_defaults_missing_counts_to_zero() -> None:
    assert TokenUsage().model_dump() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_provider_error_exposes_only_safe_context() -> None:
    from app.providers.errors import ProviderRequestError

    error = ProviderRequestError(
        "provider request failed",
        provider="zhipu",
        status_code=400,
    )

    assert str(error) == "provider request failed"
    assert error.provider == "zhipu"
    assert error.status_code == 400


def test_provider_package_exports_complete_contract() -> None:
    from app import providers

    expected_exports = {
        "BaseProvider",
        "ChatMessage",
        "ChatRequest",
        "TokenUsage",
        "ChatResponse",
        "ProviderError",
        "ProviderAuthenticationError",
        "ProviderRateLimitError",
        "ProviderServerError",
        "ProviderTimeoutError",
        "ProviderConnectionError",
        "ProviderInvalidResponseError",
        "ProviderConfigurationError",
        "ProviderRequestError",
    }

    assert expected_exports <= set(providers.__all__)
    assert all(hasattr(providers, name) for name in expected_exports)
