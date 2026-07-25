import pytest

from src.config import Settings, verify_production_secrets


def test_defaults_local():
    s = Settings(_env_file=None)
    assert s.meeting_env == "local"


def test_prod_requires_secrets():
    s = Settings(_env_file=None, meeting_env="production")
    with pytest.raises(RuntimeError):
        verify_production_secrets(s)
