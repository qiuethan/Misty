"""Tests for the Settings module (src/config.py)."""

import pytest

from src.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_tt_env_defaults_to_local(monkeypatch):
    monkeypatch.delenv("TT_ENV", raising=False)
    assert get_settings().tt_env == "local"


def test_tt_env_reads_from_environment(monkeypatch):
    monkeypatch.setenv("TT_ENV", "production")
    assert get_settings().tt_env == "production"


def test_tt_env_accepts_staging(monkeypatch):
    monkeypatch.setenv("TT_ENV", "staging")
    assert get_settings().tt_env == "staging"


def test_tt_env_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("TT_ENV", "Production")  # capital P — typo
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        get_settings()


# --- production secret guard ------------------------------------------------


def test_verify_secrets_raises_in_production_with_default_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("TT_ENV", "production")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    with pytest.raises(RuntimeError) as exc:
        verify_production_secrets()
    assert "API_KEY" in str(exc.value)


def test_verify_secrets_raises_in_staging_with_default_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("TT_ENV", "staging")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    with pytest.raises(RuntimeError):
        verify_production_secrets()


def test_verify_secrets_raises_in_production_when_api_key_unset(monkeypatch):
    """Unset API_KEY falls back to the built-in default — must still be caught."""
    from src.config import verify_production_secrets

    monkeypatch.setenv("TT_ENV", "production")
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        verify_production_secrets()


def test_verify_secrets_passes_in_local_with_default_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("TT_ENV", "local")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    verify_production_secrets()  # must not raise


def test_verify_secrets_passes_in_production_with_real_api_key(monkeypatch):
    from src.config import verify_production_secrets

    monkeypatch.setenv("TT_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-strong-unique-production-secret")
    verify_production_secrets()  # must not raise


def test_create_app_raises_in_production_with_default_api_key(monkeypatch):
    # Import first (module-level `app = create_app()` runs here under the
    # ambient local env), THEN switch to prod and clear the settings cache the
    # import repopulated — otherwise get_settings() returns cached local values.
    from src.api.app import create_app

    from src.config import DEFAULT_DEV_API_KEY

    monkeypatch.setenv("TT_ENV", "production")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        create_app()
