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
    problems: list[str] = []
    if settings.api_key == DEFAULT_DEV_API_KEY:
        problems.append("API_KEY")
    if settings.code_hmac_secret == DEFAULT_DEV_HMAC_SECRET:
        problems.append("CODE_HMAC_SECRET")
    if "dev_password@localhost" in settings.database_url:
        problems.append("DATABASE_URL")
    if settings.email_backend == "fake":
        # The fake sender silently drops mail — a non-local deploy on it would
        # 202 every request while delivering nothing.
        problems.append("EMAIL_BACKEND=fake")
    if settings.email_backend == "gmail" and not settings.gmail_sender:
        problems.append("GMAIL_SENDER")
    if settings.email_backend == "gmail" and not settings.gmail_credentials_json:
        problems.append("GMAIL_CREDENTIALS_JSON")
    if problems:
        raise RuntimeError(
            f"Refusing to start in vf_env={settings.vf_env!r}: "
            f"{', '.join(problems)} — still a built-in dev default, missing, or unsafe "
            "for a non-local deployment. Set strong, unique values via environment variables."
        )
