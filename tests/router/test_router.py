import pytest

from app.providers.base import BaseProvider
from app.providers.errors import ProviderTimeoutError
from app.providers.mock import MockProvider
from app.providers.schemas import ChatMessage, ChatRequest, ChatResponse, TokenUsage
from app.router.errors import (
    CapabilityNotFoundError,
    ModelNotRegisteredError,
    NoEnabledRouteError,
    ProviderNotRegisteredError,
)
from app.router.registry import ModelRegistry, ProviderRegistry
from app.router.schemas import ModelRegistration, RouteConfig, RouterConfig


class RecordingProvider(BaseProvider):
    def __init__(
        self, response: ChatResponse | None = None, error: Exception | None = None
    ) -> None:
        self.requests: list[ChatRequest] = []
        self.response = response
        self.error = error

    async def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def chat_request() -> ChatRequest:
    return ChatRequest(
        model="caller-model", messages=[ChatMessage(role="user", content="hello")]
    )


def make_router(
    routes: list[RouteConfig],
    *,
    registrations: list[ModelRegistration] | None = None,
    providers: dict[str, BaseProvider] | None = None,
):
    from app.router.router import ModelRouter

    config = RouterConfig(capabilities={"chat": {"routes": routes}})
    provider_registry = ProviderRegistry()
    for name, provider in (providers or {}).items():
        provider_registry.register(name, provider)
    model_registry = ModelRegistry()
    for registration in registrations or []:
        model_registry.register(registration)
    return ModelRouter(config, provider_registry, model_registry)


def route(
    channel: str,
    model: str,
    priority: int,
    *,
    provider: str = "mock",
    enabled: bool = True,
) -> RouteConfig:
    return RouteConfig(
        channel=channel,
        provider=provider,
        model=model,
        priority=priority,
        enabled=enabled,
    )


def registration(
    model: str, *, provider: str = "mock", enabled: bool = True
) -> ModelRegistration:
    return ModelRegistration(provider=provider, model=model, enabled=enabled)


def test_candidates_are_sorted_by_priority_and_returned_as_tuple() -> None:
    provider = MockProvider()
    router = make_router(
        [route("backup", "backup-model", 3), route("primary", "primary-model", 1)],
        registrations=[registration("backup-model"), registration("primary-model")],
        providers={"mock": provider},
    )

    candidates = router.candidates(" chat ")

    assert isinstance(candidates, tuple)
    assert [(c.channel, c.provider_name, c.model, c.priority) for c in candidates] == [
        ("primary", "mock", "primary-model", 1),
        ("backup", "mock", "backup-model", 3),
    ]
    assert all(candidate.provider is provider for candidate in candidates)


def test_equal_priority_preserves_configuration_order() -> None:
    router = make_router(
        [route("first", "one", 2), route("second", "two", 2)],
        registrations=[registration("one"), registration("two")],
        providers={"mock": MockProvider()},
    )

    assert [candidate.channel for candidate in router.candidates("chat")] == [
        "first",
        "second",
    ]


def test_disabled_primary_leaves_backup_first() -> None:
    router = make_router(
        [route("primary", "one", 1, enabled=False), route("backup", "two", 2)],
        registrations=[registration("two")],
        providers={"mock": MockProvider()},
    )

    assert [candidate.channel for candidate in router.candidates("chat")] == ["backup"]


def test_all_routes_disabled_raises_no_enabled_route() -> None:
    router = make_router([route("primary", "missing", 1, enabled=False)])

    with pytest.raises(NoEnabledRouteError):
        router.candidates("chat")


def test_all_registered_models_disabled_raises_no_enabled_route() -> None:
    router = make_router(
        [route("primary", "one", 1), route("backup", "two", 2)],
        registrations=[registration("one", enabled=False), registration("two", enabled=False)],
        providers={"mock": MockProvider()},
    )

    with pytest.raises(NoEnabledRouteError):
        router.candidates("chat")


@pytest.mark.parametrize("capability", ["", "   ", "missing"])
def test_blank_or_missing_capability_raises_not_found(capability: str) -> None:
    router = make_router([route("primary", "one", 1)])

    with pytest.raises(CapabilityNotFoundError):
        router.candidates(capability)


def test_enabled_unknown_provider_fails_before_backup() -> None:
    router = make_router(
        [
            route("primary", "missing", 1, provider="unknown"),
            route("backup", "two", 2),
        ],
        registrations=[registration("two")],
        providers={"mock": MockProvider()},
    )

    with pytest.raises(ProviderNotRegisteredError):
        router.candidates("chat")


def test_enabled_unknown_model_fails_before_backup() -> None:
    router = make_router(
        [route("primary", "missing", 1), route("backup", "two", 2)],
        registrations=[registration("two")],
        providers={"mock": MockProvider()},
    )

    with pytest.raises(ModelNotRegisteredError):
        router.candidates("chat")


def test_disabled_unknown_reference_is_ignored() -> None:
    router = make_router(
        [
            route("unknown-provider", "missing", 1, provider="unknown", enabled=False),
            route("unknown-model", "missing", 2, enabled=False),
            route("backup", "two", 3),
        ],
        registrations=[registration("two")],
        providers={"mock": MockProvider()},
    )

    assert [candidate.channel for candidate in router.candidates("chat")] == ["backup"]


def test_repeated_calls_leave_config_and_registries_unchanged() -> None:
    primary = MockProvider()
    config = RouterConfig(
        capabilities={
            "chat": {"routes": [route("backup", "two", 2), route("primary", "one", 1)]}
        }
    )
    providers = ProviderRegistry()
    providers.register("mock", primary)
    models = ModelRegistry()
    one = registration("one")
    two = registration("two")
    models.register(one)
    models.register(two)
    from app.router.router import ModelRouter

    router = ModelRouter(config, providers, models)
    original_config = config.model_dump()

    first = router.candidates("chat")
    second = router.candidates("chat")

    assert [candidate.channel for candidate in first] == ["primary", "backup"]
    assert second == first
    assert config.model_dump() == original_config
    assert [route.channel for route in config.capabilities["chat"].routes] == [
        "backup",
        "primary",
    ]
    assert providers.get("mock") is primary
    assert models.get("mock", "one") is one
    assert models.get("mock", "two") is two


def test_same_model_name_resolves_each_provider_registration() -> None:
    first = MockProvider()
    second = MockProvider()
    router = make_router(
        [
            route("first", "shared", 1, provider="first"),
            route("second", "shared", 2, provider="second"),
        ],
        registrations=[
            registration("shared", provider="first", enabled=False),
            registration("shared", provider="second"),
        ],
        providers={"first": first, "second": second},
    )

    candidates = router.candidates("chat")

    assert [(c.channel, c.provider_name, c.model) for c in candidates] == [
        ("second", "second", "shared")
    ]
    assert candidates[0].provider is second


@pytest.mark.anyio
async def test_route_uses_first_candidate_once_and_preserves_request() -> None:
    response = ChatResponse(
        request_id="response-1",
        provider="primary",
        model="primary-model",
        content="answer",
        latency_ms=1.0,
        usage=TokenUsage(),
    )
    primary = RecordingProvider(response=response)
    backup = RecordingProvider()
    router = make_router(
        [
            route("backup", "backup-model", 2, provider="backup"),
            route("primary", "primary-model", 1, provider="primary"),
        ],
        registrations=[
            registration("backup-model", provider="backup"),
            registration("primary-model", provider="primary"),
        ],
        providers={"primary": primary, "backup": backup},
    )
    request = chat_request()
    original = request.model_dump()

    result = await router.route(" chat ", request)

    assert result is response
    assert len(primary.requests) == 1
    assert primary.requests[0] is not request
    assert primary.requests[0].model == "primary-model"
    assert primary.requests[0].messages == request.messages
    assert request.model_dump() == original
    assert backup.requests == []


@pytest.mark.anyio
async def test_route_propagates_same_provider_timeout_without_backup() -> None:
    timeout = ProviderTimeoutError(provider="primary")
    primary = RecordingProvider(error=timeout)
    backup = RecordingProvider()
    router = make_router(
        [
            route("primary", "one", 1, provider="primary"),
            route("backup", "two", 2, provider="backup"),
        ],
        registrations=[
            registration("one", provider="primary"),
            registration("two", provider="backup"),
        ],
        providers={"primary": primary, "backup": backup},
    )

    with pytest.raises(ProviderTimeoutError) as caught:
        await router.route("chat", chat_request())

    assert caught.value is timeout
    assert len(primary.requests) == 1
    assert backup.requests == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("capability", "routes", "registrations", "expected_error"),
    [
        (
            "missing",
            [route("primary", "one", 1)],
            [registration("one")],
            CapabilityNotFoundError,
        ),
        ("chat", [route("primary", "one", 1, enabled=False)], [], NoEnabledRouteError),
        ("chat", [route("primary", "missing", 1)], [], ModelNotRegisteredError),
    ],
)
async def test_route_resolution_errors_precede_provider_invocation(
    capability: str,
    routes: list[RouteConfig],
    registrations: list[ModelRegistration],
    expected_error: type[Exception],
) -> None:
    provider = RecordingProvider()
    router = make_router(
        routes, registrations=registrations, providers={"mock": provider}
    )

    with pytest.raises(expected_error):
        await router.route(capability, chat_request())

    assert provider.requests == []


def test_router_package_exports_complete_public_api() -> None:
    import app.router as public
    from app.router.config import load_router_config
    from app.router.errors import (
        DuplicateModelError,
        DuplicateProviderError,
        RouterConfigurationError,
        RouterError,
    )
    from app.router.router import ModelRouter
    from app.router.schemas import CapabilityConfig, RouteCandidate

    expected = {
        "RouterError": RouterError,
        "RouterConfigurationError": RouterConfigurationError,
        "DuplicateProviderError": DuplicateProviderError,
        "ProviderNotRegisteredError": ProviderNotRegisteredError,
        "DuplicateModelError": DuplicateModelError,
        "ModelNotRegisteredError": ModelNotRegisteredError,
        "CapabilityNotFoundError": CapabilityNotFoundError,
        "NoEnabledRouteError": NoEnabledRouteError,
        "load_router_config": load_router_config,
        "ProviderRegistry": ProviderRegistry,
        "ModelRegistry": ModelRegistry,
        "ModelRegistration": ModelRegistration,
        "RouteConfig": RouteConfig,
        "CapabilityConfig": CapabilityConfig,
        "RouterConfig": RouterConfig,
        "RouteCandidate": RouteCandidate,
        "ModelRouter": ModelRouter,
    }

    assert set(public.__all__) == set(expected)
    assert {name: getattr(public, name) for name in public.__all__} == expected
