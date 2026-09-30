import pytest

from app.providers.mock import MockProvider
from app.router.errors import (
    CapabilityNotFoundError,
    DuplicateModelError,
    DuplicateProviderError,
    ModelNotRegisteredError,
    NoEnabledRouteError,
    ProviderNotRegisteredError,
    RouterConfigurationError,
    RouterError,
)
from app.router.registry import ModelRegistry, ProviderRegistry
from app.router.schemas import ModelRegistration


def test_router_errors_share_a_base_class() -> None:
    for error_type in (
        RouterConfigurationError,
        DuplicateProviderError,
        ProviderNotRegisteredError,
        DuplicateModelError,
        ModelNotRegisteredError,
        CapabilityNotFoundError,
        NoEnabledRouteError,
    ):
        assert issubclass(error_type, RouterError)


def test_provider_lookup_returns_exact_instance_after_trimming_name() -> None:
    registry = ProviderRegistry()
    provider = MockProvider()

    registry.register(" mock ", provider)

    assert registry.get("  mock  ") is provider


def test_provider_rejects_normalized_duplicate() -> None:
    registry = ProviderRegistry()
    registry.register(" mock ", MockProvider())

    with pytest.raises(DuplicateProviderError, match="^provider already registered$"):
        registry.register("mock", MockProvider())


@pytest.mark.parametrize("name", ["", "  "])
def test_provider_rejects_blank_registration_name(name: str) -> None:
    with pytest.raises(RouterConfigurationError, match="^provider name must not be blank$"):
        ProviderRegistry().register(name, MockProvider())


def test_provider_rejects_wrong_type_without_exposing_object() -> None:
    secret = "super-secret-token"

    class UnsafeObject:
        def __repr__(self) -> str:
            return secret

    with pytest.raises(RouterConfigurationError) as caught:
        ProviderRegistry().register("mock", UnsafeObject())  # type: ignore[arg-type]

    assert str(caught.value) == "provider must be a BaseProvider"
    assert secret not in str(caught.value)


@pytest.mark.parametrize("name", ["", "  ", "missing"])
def test_provider_lookup_reports_missing_or_blank_name(name: str) -> None:
    with pytest.raises(ProviderNotRegisteredError, match="^provider not registered$"):
        ProviderRegistry().get(name)


def test_two_providers_can_register_same_model_name() -> None:
    registry = ModelRegistry()
    first = ModelRegistration(provider="first", model="shared")
    second = ModelRegistration(provider="second", model="shared")

    registry.register(first)
    registry.register(second)

    assert registry.get(" first ", " shared ") is first
    assert registry.get("second", "shared") is second


def test_model_rejects_duplicate_provider_model_pair() -> None:
    registry = ModelRegistry()
    registry.register(ModelRegistration(provider=" mock ", model=" shared "))

    with pytest.raises(DuplicateModelError, match="^model already registered$"):
        registry.register(ModelRegistration(provider="mock", model="shared"))


@pytest.mark.parametrize(
    "provider, model",
    [("", "shared"), ("  ", "shared"), ("mock", ""), ("mock", "  "), ("other", "shared"), ("mock", "other")],
)
def test_model_lookup_reports_missing_or_blank_key(provider: str, model: str) -> None:
    registry = ModelRegistry()
    registry.register(ModelRegistration(provider="mock", model="shared"))

    with pytest.raises(ModelNotRegisteredError, match="^model not registered$"):
        registry.get(provider, model)
