import pytest

from src.config import Settings, verify_production_secrets


def test_local_env_never_raises():
    verify_production_secrets(Settings(llm_env="local"))  # no raise


def test_production_with_default_key_raises():
    s = Settings(llm_env="production", api_key="dev-api-key-change-me", aws_region="us-east-1")
    with pytest.raises(RuntimeError, match="API_KEY"):
        verify_production_secrets(s)


def test_production_with_empty_region_raises():
    s = Settings(llm_env="production", api_key="strong-unique-key", aws_region="")
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        verify_production_secrets(s)


def test_production_fully_configured_ok():
    s = Settings(llm_env="production", api_key="strong-unique-key", aws_region="us-east-1")
    verify_production_secrets(s)  # no raise


def test_malformed_consumer_keys_fails_on_boot(monkeypatch):
    from src.api import deps
    from src.config import get_settings

    monkeypatch.setenv("CONSUMER_KEYS", "{not valid json")
    get_settings.cache_clear()
    deps._key_store.cache_clear()
    from src.api.app import create_app

    with pytest.raises(RuntimeError, match="CONSUMER_KEYS"):
        create_app()

    deps._key_store.cache_clear()
    get_settings.cache_clear()
