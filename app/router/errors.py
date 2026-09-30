class RouterError(Exception):
    """Base error for router configuration and lookup failures."""


class RouterConfigurationError(RouterError):
    """Invalid router configuration."""


class DuplicateProviderError(RouterConfigurationError):
    """A provider name is already registered."""


class ProviderNotRegisteredError(RouterError):
    """A provider lookup did not find a registration."""


class DuplicateModelError(RouterConfigurationError):
    """A provider/model pair is already registered."""


class ModelNotRegisteredError(RouterError):
    """A model lookup did not find a registration."""


class CapabilityNotFoundError(RouterError):
    """A requested capability is unavailable."""


class NoEnabledRouteError(RouterError):
    """No enabled route exists for a capability."""
