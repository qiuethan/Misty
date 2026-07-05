from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_API_KEY = "dev-api-key-change-me"
DEFAULT_DEV_HMAC_SECRET = "dev-hmac-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://verification:dev_password@localhost:5434/verification"
    api_key: str = DEFAULT_DEV_API_KEY
    code_hmac_secret: str = DEFAULT_DEV_HMAC_SECRET
    vf_env: Literal["local", "staging", "production"] = "local"
    email_backend: Literal["fake", "gmail"] = "fake"
    gmail_sender: str = ""
    gmail_credentials_json: str = ""  # base64-encoded service-account JSON


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def verify_production_secrets(settings: Settings | None = None) -> None:
    """Fail fast if a non-local environment still uses built-in dev secrets."""
    settings = settings or get_settings()
    if settings.vf_env == "local":
        return
    insecure: list[str] = []
    if settings.api_key == DEFAULT_DEV_API_KEY:
        insecure.append("API_KEY")
    if settings.code_hmac_secret == DEFAULT_DEV_HMAC_SECRET:
        insecure.append("CODE_HMAC_SECRET")
    if settings.email_backend == "gmail" and not settings.gmail_sender:
        insecure.append("GMAIL_SENDER")
    if settings.email_backend == "gmail" and not settings.gmail_credentials_json:
        insecure.append("GMAIL_CREDENTIALS_JSON")
    if insecure:
        raise RuntimeError(
            f"Refusing to start in vf_env={settings.vf_env!r}: "
            f"{', '.join(insecure)} missing or still the built-in dev default. "
            "Set strong, unique values via environment variables."
        )
