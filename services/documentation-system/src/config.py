from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# The built-in dev secret, shared by the inbound API key and the outbound
# directory key. Only acceptable when docs_env == "local"; any other
# environment must override these with strong values (see
# verify_production_secrets). Shipping the default `api_key` to
# staging/production would accept a publicly-known admin key via the
# env-bootstrap auth path.
DEFAULT_DEV_API_KEY = "dev-api-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://docs:dev_password@localhost:5434/docs"
    )
    api_key: str = DEFAULT_DEV_API_KEY
    directory_base_url: str = "http://localhost:8000"
    directory_api_key: str = DEFAULT_DEV_API_KEY
    docs_env: Literal["local", "staging", "production"] = "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def verify_production_secrets(settings: Settings | None = None) -> None:
    """Fail fast if a non-local environment is still using built-in dev secrets.

    `api_key` is the inbound env-bootstrap admin key (src/api/auth.py); when it
    is the committed default it is publicly known. `directory_api_key` is the
    outbound credential this service presents to the directory service; a
    default there is a broken prod config. Called from create_app(), so a
    misconfigured deploy dies at startup, not on first request.
    """
    settings = settings or get_settings()
    if settings.docs_env == "local":
        return
    insecure: list[str] = []
    if settings.api_key == DEFAULT_DEV_API_KEY:
        insecure.append("API_KEY")
    if settings.directory_api_key == DEFAULT_DEV_API_KEY:
        insecure.append("DIRECTORY_API_KEY")
    if insecure:
        raise RuntimeError(
            f"Refusing to start in docs_env={settings.docs_env!r}: "
            f"{', '.join(insecure)} still set to the built-in dev default. "
            "Set a strong, unique value via environment variables."
        )
