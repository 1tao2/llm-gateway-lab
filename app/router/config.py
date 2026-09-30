from pathlib import Path

import yaml
from pydantic import ValidationError

from app.router.errors import RouterConfigurationError
from app.router.schemas import RouterConfig


def load_router_config(path: Path) -> RouterConfig:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return RouterConfig.model_validate(data)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RouterConfigurationError(f"无法加载路由配置: {path}") from exc
