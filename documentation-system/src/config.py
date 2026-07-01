from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://docs:dev_password@localhost:5434/docs"
    )
    api_key: str = "dev-api-key-change-me"
    directory_base_url: str = "http://localhost:8000"
    directory_api_key: str = "dev-api-key-change-me"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
