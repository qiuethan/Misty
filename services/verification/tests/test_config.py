import pytest

from src.config import (
    DEFAULT_DEV_API_KEY,
    DEFAULT_DEV_HMAC_SECRET,
    Settings,
    verify_production_secrets,
)


def _prod(**overrides) -> Settings:
    base = dict(
        vf_env="staging",
        api_key="a-strong-api-key",
        code_hmac_secret="a-strong-hmac-secret",
        database_url="postgresql+psycopg://user:pass@prod-host:5432/verification",
        email_backend="gmail",
        gmail_sender="noreply@utmist.ca",
        gmail_credentials_json="base64creds",
    )
    base.update(overrides)
    return Settings(**base)


def test_local_env_always_passes():
    # Dev defaults are acceptable locally — the guard is a no-op.
    verify_production_secrets(Settings(vf_env="local"))


def test_prod_passes_with_strong_config():
    verify_production_secrets(_prod())  # must not raise


def test_prod_rejects_dev_database_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        verify_production_secrets(
            _prod(
                database_url="postgresql+psycopg://verification:dev_password@localhost:5434/verification"
            )
        )


def test_prod_rejects_fake_email_backend():
    with pytest.raises(RuntimeError, match="EMAIL_BACKEND=fake"):
        verify_production_secrets(_prod(email_backend="fake"))


def test_prod_rejects_dev_api_key():
    with pytest.raises(RuntimeError, match="API_KEY"):
        verify_production_secrets(_prod(api_key=DEFAULT_DEV_API_KEY))


def test_prod_rejects_dev_hmac_secret():
    with pytest.raises(RuntimeError, match="CODE_HMAC_SECRET"):
        verify_production_secrets(_prod(code_hmac_secret=DEFAULT_DEV_HMAC_SECRET))


def test_prod_rejects_gmail_backend_without_credentials():
    with pytest.raises(RuntimeError, match="GMAIL_CREDENTIALS_JSON"):
        verify_production_secrets(_prod(gmail_credentials_json=""))
