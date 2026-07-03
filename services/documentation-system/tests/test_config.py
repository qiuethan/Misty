from src.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.directory_base_url.startswith("http")
    assert s.api_key
