from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Built-in dev secret. Only acceptable when llm_env == "local"; any other
# environment must override API_KEY (see verify_production_secrets), because the
# env-bootstrap auth path grants admin scope to whoever presents this value.
DEFAULT_DEV_API_KEY = "dev-api-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_env: Literal["local", "staging", "production"] = "local"
    api_key: str = DEFAULT_DEV_API_KEY
    # JSON array of consumer keys: [{"name","prefix","key_hash","scopes"?}]
    consumer_keys: str = ""
    llm_provider: str = "bedrock"
    llm_model: str = "claude-sonnet-5"
    aws_region: str = ""
    request_timeout_s: float = 60.0
    thinking_default: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def verify_production_secrets(settings: Settings | None = None) -> None:
    """Fail fast if a non-local environment is still misconfigured.

    Called from create_app(), so a bad deploy dies at startup, not first request.
    """
    settings = settings or get_settings()
    if settings.llm_env == "local":
        return
    insecure: list[str] = []
    if settings.api_key == DEFAULT_DEV_API_KEY:
        insecure.append("API_KEY")
    if not settings.aws_region:
        insecure.append("AWS_REGION")
    if insecure:
        raise RuntimeError(
            f"Refusing to start in llm_env={settings.llm_env!r}: "
            f"{', '.join(insecure)} not set to a real value."
        )
