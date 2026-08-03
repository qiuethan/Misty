import pytest

from src.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_defaults():
    s = Settings()
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.directory_base_url.startswith("http")
    assert s.api_key


# --- docs_env -----------------------------------------------------------------


def test_docs_env_defaults_to_local(monkeypatch):
    monkeypatch.delenv("DOCS_ENV", raising=False)
    assert get_settings().docs_env == "local"


def test_docs_env_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DOCS_ENV", "production")
    assert get_settings().docs_env == "production"


def test_docs_env_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("DOCS_ENV", "Production")  # capital P — typo
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        get_settings()


# --- production secret guard --------------------------------------------------


def test_verify_secrets_raises_in_production_with_default_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "production")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    monkeypatch.setenv("DIRECTORY_API_KEY", "a-strong-directory-secret")
    with pytest.raises(RuntimeError) as exc:
        verify_production_secrets()
    assert "API_KEY" in str(exc.value)


def test_verify_secrets_raises_in_production_with_default_directory_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-strong-api-secret")
    monkeypatch.setenv("DIRECTORY_API_KEY", DEFAULT_DEV_API_KEY)
    with pytest.raises(RuntimeError) as exc:
        verify_production_secrets()
    assert "DIRECTORY_API_KEY" in str(exc.value)


def test_verify_secrets_warns_in_production_with_default_connectors_api_key(
    monkeypatch, caplog
):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-strong-api-secret")
    monkeypatch.setenv("DIRECTORY_API_KEY", "a-strong-directory-secret")
    monkeypatch.setenv("CONNECTORS_API_KEY", DEFAULT_DEV_API_KEY)
    with caplog.at_level("WARNING"):
        verify_production_secrets()  # must not raise
    assert any("CONNECTORS_API_KEY" in record.message for record in caplog.records)


def test_verify_secrets_no_connectors_warning_in_local(monkeypatch, caplog):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "local")
    monkeypatch.setenv("CONNECTORS_API_KEY", DEFAULT_DEV_API_KEY)
    with caplog.at_level("WARNING"):
        verify_production_secrets()  # must not raise
    assert not any("CONNECTORS_API_KEY" in record.message for record in caplog.records)


def test_verify_secrets_raises_in_staging_with_default_api_key(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "staging")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    with pytest.raises(RuntimeError):
        verify_production_secrets()


def test_verify_secrets_passes_in_local_with_default_secrets(monkeypatch):
    from src.config import DEFAULT_DEV_API_KEY, verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "local")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    monkeypatch.setenv("DIRECTORY_API_KEY", DEFAULT_DEV_API_KEY)
    verify_production_secrets()  # must not raise


def test_verify_secrets_passes_in_production_with_real_secrets(monkeypatch):
    from src.config import verify_production_secrets

    monkeypatch.setenv("DOCS_ENV", "production")
    monkeypatch.setenv("API_KEY", "a-strong-api-secret")
    monkeypatch.setenv("DIRECTORY_API_KEY", "a-strong-directory-secret")
    monkeypatch.setenv("CONNECTORS_API_KEY", "a-strong-connectors-secret")
    verify_production_secrets()  # must not raise


def test_create_app_raises_in_production_with_default_api_key(monkeypatch):
    from src.api.app import create_app

    from src.config import DEFAULT_DEV_API_KEY

    monkeypatch.setenv("DOCS_ENV", "production")
    monkeypatch.setenv("API_KEY", DEFAULT_DEV_API_KEY)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        create_app()
