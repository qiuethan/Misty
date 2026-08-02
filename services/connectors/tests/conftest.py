import pytest


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch):
    """Never let the suite read a developer's local .env.

    Settings.model_config declares env_file=".env", so any test that builds
    Settings() or calls get_settings() would otherwise silently inherit
    whatever a developer has locally configured (e.g. a real
    GOOGLE_CREDENTIALS_JSON), producing failures unrelated to the change
    under test. Neutralizing env_file here — before any cached Settings are
    built — makes the suite hermetic regardless of what's on disk.
    """
    from src.config import Settings

    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def _clear_settings_cache(_no_dotenv):
    from src.api import deps
    from src.config import get_settings

    get_settings.cache_clear()
    deps._key_store.cache_clear()
    deps._source_registry.cache_clear()
    yield
    get_settings.cache_clear()
    deps._key_store.cache_clear()
    deps._source_registry.cache_clear()
