import pytest
from pydantic import ValidationError

from app.config import Settings


SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_ENV",
    "HOST",
    "PORT",
    "LOG_LEVEL",
    "ZHIPU_API_KEY",
    "ZHIPU_BASE_URL",
    "ZHIPU_CHAT_MODEL",
    "PROVIDER_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_use_safe_defaults_without_api_key() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "LLM Gateway Lab"
    assert settings.app_env == "local"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.log_level == "INFO"
    assert settings.zhipu_api_key is None
    assert settings.zhipu_base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert settings.zhipu_chat_model == "glm-4-flash"
    assert settings.provider_timeout_seconds == 30.0


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ZHIPU_API_KEY", "test-placeholder")
    monkeypatch.setenv("ZHIPU_BASE_URL", "https://example.invalid/v4")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "glm-test")
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "12.5")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"
    assert settings.zhipu_api_key == "test-placeholder"
    assert settings.zhipu_base_url == "https://example.invalid/v4"
    assert settings.zhipu_chat_model == "glm-test"
    assert settings.provider_timeout_seconds == 12.5


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_invalid_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    monkeypatch.setenv("PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("timeout", ["0", "-1", "not-a-number"])
def test_invalid_provider_timeout_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
