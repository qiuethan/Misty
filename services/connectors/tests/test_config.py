import pytest

from src.config import DEFAULT_DEV_API_KEY, Settings, verify_production_secrets


def test_defaults_are_local_and_dev():
    s = Settings()
    assert s.connectors_env == "local"
    assert s.api_key == DEFAULT_DEV_API_KEY
    assert s.google_credentials_json == ""


def test_production_with_dev_api_key_is_refused():
    s = Settings(connectors_env="production", api_key=DEFAULT_DEV_API_KEY)
    with pytest.raises(RuntimeError, match="API_KEY"):
        verify_production_secrets(s)


def test_production_with_strong_key_passes():
    s = Settings(connectors_env="production", api_key="a-strong-unique-value")
    verify_production_secrets(s)


def test_missing_google_credentials_never_blocks_startup():
    # A connectors service that cannot reach Drive is degraded, not broken.
    s = Settings(connectors_env="production", api_key="strong", google_credentials_json="")
    verify_production_secrets(s)
