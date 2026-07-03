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
