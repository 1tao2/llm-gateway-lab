from app.providers.schemas import ChatRequest, ChatResponse
from app.router.errors import CapabilityNotFoundError, NoEnabledRouteError
from app.router.registry import ModelRegistry, ProviderRegistry
from app.router.schemas import RouteCandidate, RouterConfig


class ModelRouter:
    def __init__(
        self, config: RouterConfig, providers: ProviderRegistry, models: ModelRegistry
    ) -> None:
        self._config = config
        self._providers = providers
        self._models = models

    def candidates(self, capability: str) -> tuple[RouteCandidate, ...]:
        name = capability.strip()
        if not name or name not in self._config.capabilities:
            raise CapabilityNotFoundError("capability not found")

        candidates: list[tuple[int, RouteCandidate]] = []
        for index, route in enumerate(self._config.capabilities[name].routes):
            if not route.enabled:
                continue
            provider = self._providers.get(route.provider)
            registration = self._models.get(route.provider, route.model)
            if not registration.enabled:
                continue
            candidates.append(
                (
                    index,
                    RouteCandidate(
                        channel=route.channel,
                        provider_name=route.provider,
                        model=route.model,
                        priority=route.priority,
                        provider=provider,
                    ),
                )
            )
        if not candidates:
            raise NoEnabledRouteError("no enabled route")
        candidates.sort(key=lambda item: (item[1].priority, item[0]))
        return tuple(candidate for _, candidate in candidates)

    async def route(self, capability: str, request: ChatRequest) -> ChatResponse:
        candidate = self.candidates(capability)[0]
        routed_request = request.model_copy(update={"model": candidate.model})
        return await candidate.provider.chat(routed_request)
