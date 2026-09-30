import pytest
from pydantic import ValidationError

from app.providers.mock import MockProvider
from app.router.schemas import (
    CapabilityConfig,
    ModelRegistration,
    RouteCandidate,
    RouteConfig,
    RouterConfig,
)


def route(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "channel": "chat",
        "provider": "mock",
        "model": "mock-model",
        "priority": 1,
    }
    values.update(overrides)
    return values


def test_registration_names_are_trimmed() -> None:
    registration = ModelRegistration(provider=" mock ", model=" model ")

    assert registration.provider == "mock"
    assert registration.model == "model"
    assert registration.enabled is True


def test_route_names_and_capability_key_are_trimmed_without_mutating_input() -> None:
    raw = {" chat ": {"routes": [route(channel=" chat ", provider=" mock ", model=" model ")]}}

    config = RouterConfig(capabilities=raw)

    assert list(config.capabilities) == ["chat"]
    assert raw == {" chat ": {"routes": [route(channel=" chat ", provider=" mock ", model=" model ")]}}
    route_config = config.capabilities["chat"].routes[0]
    assert (route_config.channel, route_config.provider, route_config.model) == (
        "chat",
        "mock",
        "model",
    )
    assert route_config.enabled is True


@pytest.mark.parametrize("priority", [0, -1])
def test_route_rejects_nonpositive_priority(priority: int) -> None:
    with pytest.raises(ValidationError):
        RouteConfig(**route(priority=priority))


def test_capability_rejects_empty_routes() -> None:
    with pytest.raises(ValidationError):
        CapabilityConfig(routes=[])


def test_router_rejects_empty_capabilities() -> None:
    with pytest.raises(ValidationError):
        RouterConfig(capabilities={})


@pytest.mark.parametrize("key", ["", "  "])
def test_router_rejects_blank_capability_key(key: str) -> None:
    with pytest.raises(ValidationError):
        RouterConfig(capabilities={key: {"routes": [route()]}})


def test_router_rejects_keys_colliding_after_normalization() -> None:
    capabilities = {
        "chat": {"routes": [route()]},
        " chat ": {"routes": [route()]},
    }

    with pytest.raises(ValidationError):
        RouterConfig(capabilities=capabilities)

    assert len(capabilities) == 2


@pytest.mark.parametrize(
    "model_type, data",
    [
        (ModelRegistration, {"provider": "mock", "model": "model"}),
        (RouteConfig, route()),
        (CapabilityConfig, {"routes": [route()]}),
        (RouterConfig, {"capabilities": {"chat": {"routes": [route()]}}}),
        (
            RouteCandidate,
            {
                "channel": "chat",
                "provider_name": "mock",
                "model": "model",
                "priority": 1,
                "provider": MockProvider(),
            },
        ),
    ],
)
def test_models_reject_extra_fields(model_type: type, data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model_type(**data, unexpected=True)


@pytest.mark.parametrize(
    "model_type, data",
    [
        (ModelRegistration, {"provider": " ", "model": "model"}),
        (RouteConfig, route(model=" ")),
        (
            RouteCandidate,
            {
                "channel": " ",
                "provider_name": "mock",
                "model": "model",
                "priority": 1,
                "provider": MockProvider(),
            },
        ),
    ],
)
def test_models_reject_blank_names(model_type: type, data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model_type(**data)


def test_route_candidate_accepts_mock_provider_and_is_frozen() -> None:
    provider = MockProvider()
    candidate = RouteCandidate(
        channel=" chat ",
        provider_name=" mock ",
        model=" model ",
        priority=1,
        provider=provider,
    )

    assert candidate.provider is provider
    assert (candidate.channel, candidate.provider_name, candidate.model) == (
        "chat",
        "mock",
        "model",
    )
    with pytest.raises(ValidationError):
        candidate.model = "another-model"
