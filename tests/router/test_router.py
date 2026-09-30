import pytest

from app.providers.mock import MockProvider
from app.router.errors import (
    CapabilityNotFoundError,
    ModelNotRegisteredError,
    NoEnabledRouteError,
    ProviderNotRegisteredError,
)
from app.router.registry import ModelRegistry, ProviderRegistry
from app.router.schemas import ModelRegistration, RouteConfig, RouterConfig


def make_router(
    routes: list[RouteConfig],
    *,
    registrations: list[ModelRegistration] | None = None,
    providers: dict[str, MockProvider] | None = None,
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
