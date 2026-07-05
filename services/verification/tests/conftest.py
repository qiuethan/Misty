import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.deps import get_email_sender, get_storage
from src.email.fake import FakeSender
from src.storage.in_memory import InMemoryVerificationStore

ENV_KEY = "test-vf-key"
AUTH = {"X-API-Key": ENV_KEY}


@pytest.fixture
def store() -> InMemoryVerificationStore:
    return InMemoryVerificationStore()


@pytest.fixture
def email() -> FakeSender:
    return FakeSender()


@pytest.fixture
def client(monkeypatch, store, email):
    monkeypatch.setenv("API_KEY", ENV_KEY)
    monkeypatch.setenv("CODE_HMAC_SECRET", "test-hmac-secret")
    from src.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_email_sender] = lambda: email
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
