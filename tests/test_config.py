import pytest
from pydantic import ValidationError

from app.config import Settings


SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_ENV",
    "HOST",
    "PORT",
    "LOG_LEVEL",
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


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_env == "test"
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize("port", ["0", "65536", "not-a-number"])
def test_invalid_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    monkeypatch.setenv("PORT", port)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
