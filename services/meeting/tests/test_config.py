import pytest

from src.config import Settings, verify_production_secrets


def test_defaults_local():
    s = Settings(_env_file=None)
    assert s.meeting_env == "local"


def test_max_meeting_ms_defaults_to_4h_backstop():
    # A 4h safety cap backstops worst-case memory; the normal end is /record
    # stop or auto-stop-on-empty. Can be overridden, or set to None to disable.
    s = Settings(_env_file=None)
    assert s.max_meeting_ms == 14_400_000


def test_max_meeting_ms_is_overridable_and_validated():
    assert Settings(_env_file=None, max_meeting_ms=60_000).max_meeting_ms == 60_000
    assert Settings(_env_file=None, max_meeting_ms=None).max_meeting_ms is None  # disable
    with pytest.raises(ValueError):
        Settings(_env_file=None, max_meeting_ms=0)  # gt=0 still enforced


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
