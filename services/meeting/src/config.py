from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Built-in dev secret. Only acceptable when meeting_env == "local"; any other
# environment must override API_KEY (see verify_production_secrets), because the
# env-bootstrap auth path grants admin scope to whoever presents this value.
DEFAULT_DEV_API_KEY = "dev-api-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    meeting_env: Literal["local", "staging", "production"] = "local"
    api_key: str = DEFAULT_DEV_API_KEY
    # JSON array of consumer keys: [{"name","prefix","key_hash","scopes"?}]
    consumer_keys: str = ""
    aws_region: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    request_timeout_s: float = Field(default=60.0, gt=0)
    # Safety cap (see sessions.py MeetingSession.feed): once a meeting exceeds
    # this many ms, further audio frames are dropped. This is a BACKSTOP, not
    # the normal end condition -- recordings usually end on /record stop or
    # auto-stop-on-empty (the bot ends a recording when everyone leaves the voice
    # channel). The cap bounds worst-case memory because the current design
        # (Misty #121). Set MAX_MEETING_MS to another value, or None, to change or
    # disable it.
    max_meeting_ms: int | None = Field(default=14_400_000, gt=0)  # 4 hours


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def verify_production_secrets(settings: Settings | None = None) -> None:
    """Fail fast if a non-local environment is still misconfigured.

    Called from create_app(), so a bad deploy dies at startup, not first request.
    """
    settings = settings or get_settings()
    if settings.meeting_env == "local":
        return
    insecure: list[str] = []
    if settings.api_key == DEFAULT_DEV_API_KEY:
        insecure.append("API_KEY")
    if not settings.aws_region:
        insecure.append("AWS_REGION")
    if not settings.llm_base_url:
        insecure.append("LLM_BASE_URL")
    if not settings.llm_api_key:
        insecure.append("LLM_API_KEY")
    if insecure:
        raise RuntimeError(
            f"Refusing to start in meeting_env={settings.meeting_env!r}: "
            f"{', '.join(insecure)} not set to a real value."
        )
