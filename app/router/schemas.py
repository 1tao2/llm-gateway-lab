from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.providers.base import BaseProvider

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ModelRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Name
    model: Name
    enabled: bool = True


class RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Name
    provider: Name
    model: Name
    priority: int = Field(gt=0)
    enabled: bool = True


class CapabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routes: list[RouteConfig] = Field(min_length=1)


class RouterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: dict[str, CapabilityConfig] = Field(min_length=1)

    @field_validator("capabilities", mode="before")
    @classmethod
    def normalize_capability_keys(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        normalized = {}
        for key, capability in value.items():
            if not isinstance(key, str):
                return value
            name = key.strip()
            if not name:
                raise ValueError("capability name must not be blank")
            if name in normalized:
                raise ValueError(f"duplicate capability name: {name}")
            normalized[name] = capability
        return normalized


class RouteCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, arbitrary_types_allowed=True
    )

    channel: Name
    provider_name: Name
    model: Name
    priority: int = Field(gt=0)
    provider: BaseProvider
