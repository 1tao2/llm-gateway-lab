from pathlib import Path

import yaml
from pydantic import ValidationError

from app.router.errors import RouterConfigurationError
from app.router.schemas import RouterConfig


def load_router_config(path: Path) -> RouterConfig:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = RouterConfig.model_validate(data)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError):
        config = None
    # 离开 except 后抛出，避免异常链保留配置内容或校验详情。
    if config is None:
        raise RouterConfigurationError(f"无法加载路由配置: {path}")
    return config
