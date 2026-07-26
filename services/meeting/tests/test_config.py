import pytest

from src.config import Settings, verify_production_secrets


def test_defaults_local():
    s = Settings(_env_file=None)
    assert s.meeting_env == "local"


def test_prod_requires_secrets():
    s = Settings(_env_file=None, meeting_env="production")
    with pytest.raises(RuntimeError):
        verify_production_secrets(s)


def test_prod_requires_llm_api_key():
    s = Settings(
        _env_file=None,
        meeting_env="production",
        api_key="real-key",
        aws_region="us-east-1",
        llm_base_url="https://llm.example.com",
        llm_api_key="",
    )
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        verify_production_secrets(s)
