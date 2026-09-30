from app.providers.base import BaseProvider
from app.router.errors import (
    DuplicateModelError,
    DuplicateProviderError,
    ModelNotRegisteredError,
    ProviderNotRegisteredError,
    RouterConfigurationError,
)
from app.router.schemas import ModelRegistration


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider) -> None:
        if not isinstance(name, str) or not name.strip():
            raise RouterConfigurationError("provider name must not be blank")
        if not isinstance(provider, BaseProvider):
            raise RouterConfigurationError("provider must be a BaseProvider")

        normalized_name = name.strip()
        if normalized_name in self._providers:
            raise DuplicateProviderError("provider already registered")
        self._providers[normalized_name] = provider

    def get(self, name: str) -> BaseProvider:
        if not isinstance(name, str):
            raise ProviderNotRegisteredError("provider not registered")
        try:
            return self._providers[name.strip()]
        except KeyError:
            raise ProviderNotRegisteredError("provider not registered") from None


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[tuple[str, str], ModelRegistration] = {}

    def register(self, registration: ModelRegistration) -> None:
        if not isinstance(registration, ModelRegistration):
            raise RouterConfigurationError("registration must be a ModelRegistration")

        key = (registration.provider, registration.model)
        if key in self._models:
            raise DuplicateModelError("model already registered")
        self._models[key] = registration

    def get(self, provider: str, model: str) -> ModelRegistration:
        if not isinstance(provider, str) or not isinstance(model, str):
            raise ModelNotRegisteredError("model not registered")
        key = (provider.strip(), model.strip())
        try:
            return self._models[key]
        except KeyError:
            raise ModelNotRegisteredError("model not registered") from None
