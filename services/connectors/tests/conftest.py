import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from src.api import deps
    from src.config import get_settings

    get_settings.cache_clear()
    deps._key_store.cache_clear()
    deps._source_registry.cache_clear()
    yield
    get_settings.cache_clear()
    deps._key_store.cache_clear()
    deps._source_registry.cache_clear()
