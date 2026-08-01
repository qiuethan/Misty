from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Built-in dev secret. Only acceptable when connectors_env == "local"; any other
# environment must override API_KEY (see verify_production_secrets), because the
# env-bootstrap auth path grants admin scope to whoever presents this value.
DEFAULT_DEV_API_KEY = "dev-api-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    connectors_env: Literal["local", "staging", "production"] = "local"
    api_key: str = DEFAULT_DEV_API_KEY
    # JSON array of consumer keys: [{"name","prefix","key_hash","scopes"?}]
    consumer_keys: str = ""
    # base64-encoded Google service-account JSON. Empty is a valid running
    # state: Google fetches then fail as SourceNotConfigured (503) while the
    # rest of the service keeps serving.
    google_credentials_json: str = ""
    # Transport guard only. documentation-system's own clamp decides what is
    # actually stored; this just stops a pathological file becoming a huge
    # HTTP response.
    max_content_chars: int = Field(default=1_000_000, gt=0)
    request_timeout_s: float = Field(default=30.0, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def verify_production_secrets(settings: Settings | None = None) -> None:
    """Fail fast if a non-local environment still uses the built-in dev secret.

    Google credentials are deliberately NOT checked here: a connectors service
    that cannot reach Drive is degraded, not broken, and must still start and
    serve /health so it can be deployed before the service account exists.
    """
    settings = settings or get_settings()
    if settings.connectors_env == "local":
        return
    if settings.api_key == DEFAULT_DEV_API_KEY:
        raise RuntimeError(
            f"Refusing to start in connectors_env={settings.connectors_env!r}: "
            "API_KEY still set to the built-in dev default. "
            "Set a strong, unique value via environment variables."
        )
