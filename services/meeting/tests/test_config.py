import pytest

from src.config import Settings, verify_production_secrets


def test_defaults_local():
    s = Settings(_env_file=None)
    assert s.meeting_env == "local"


def test_max_meeting_ms_defaults_to_none_no_cap():
    # No default length cap: a meeting runs until /record stop or auto-stop-on-
    # empty. MAX_MEETING_MS can still be set to re-enable a hard bound.
    s = Settings(_env_file=None)
    assert s.max_meeting_ms is None


def test_max_meeting_ms_still_validates_when_set():
    assert Settings(_env_file=None, max_meeting_ms=60_000).max_meeting_ms == 60_000
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
