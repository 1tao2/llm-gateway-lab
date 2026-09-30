from pathlib import Path

import pytest

from app.router.config import load_router_config
from app.router.errors import RouterConfigurationError


def test_load_valid_router_config(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "capabilities:\n"
        "  text_generation:\n"
        "    routes:\n"
        "      - channel: chat\n"
        "        provider: mock\n"
        "        model: mock-primary\n"
        "        priority: 1\n",
        encoding="utf-8",
    )

    config = load_router_config(path)

    route = config.capabilities["text_generation"].routes[0]
    assert (route.channel, route.provider, route.model, route.priority, route.enabled) == (
        "chat", "mock", "mock-primary", 1, True
    )


def test_missing_file_has_safe_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"

    with pytest.raises(RouterConfigurationError) as error:
        load_router_config(path)

    assert str(error.value) == f"无法加载路由配置: {path}"
    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize(
    "contents",
    [
        "capabilities: [unclosed",
        "secret-scalar",
        "[secret-list]",
        "null",
        "capabilities: {}\n# secret-empty",
        "capabilities:\n  text_generation:\n    routes:\n"
        "      - channel: chat\n        provider: mock\n"
        "        model: mock-primary\n        priority: 1\n"
        "        illegal: secret-field",
    ],
    ids=["malformed", "scalar", "list", "null", "empty-capabilities", "illegal-field"],
)
def test_invalid_yaml_has_safe_configuration_error(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(RouterConfigurationError) as error:
        load_router_config(path)

    assert str(error.value) == f"无法加载路由配置: {path}"
    assert error.value.__cause__ is not None
    assert contents not in str(error.value)
    assert "secret" not in str(error.value)


def test_loads_utf8_content(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "capabilities:\n"
        "  文本生成:\n"
        "    routes:\n"
        "      - channel: 中文通道\n"
        "        provider: mock\n"
        "        model: 测试模型\n"
        "        priority: 1\n",
        encoding="utf-8",
    )

    config = load_router_config(path)

    route = config.capabilities["文本生成"].routes[0]
    assert (route.channel, route.model) == ("中文通道", "测试模型")


def test_sample_routes_have_exact_primary_and_backup_metadata() -> None:
    path = Path(__file__).resolve().parents[2] / "configs" / "models.yaml"

    config = load_router_config(path)

    assert list(config.capabilities) == ["text_generation"]
    routes = config.capabilities["text_generation"].routes
    assert [
        (route.channel, route.provider, route.model, route.priority, route.enabled)
        for route in routes
    ] == [
        ("primary", "mock", "mock-primary", 1, True),
        ("backup", "zhipu", "glm-4-flash", 2, False),
    ]
