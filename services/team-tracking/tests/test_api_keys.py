"""Tests for GET /api-keys/self — key self-introspection."""

import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.api.hashing import generate_key
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def adapter():
    return InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())


@pytest.fixture
def client(monkeypatch, adapter):
    monkeypatch.setenv("API_KEY", "env-bootstrap-key-value")
    from src.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _issue(adapter, name: str, scopes: list[str]) -> str:
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(name=name, prefix=prefix, key_hash=key_hash, scopes=scopes, actor="test")
    return plaintext


def test_self_returns_key_metadata(client, adapter):
    plaintext = _issue(adapter, "discord-bot", ["people:read", "people:write"])
    resp = client.get("/api-keys/self", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200
    assert resp.json() == {
        "name": "discord-bot",
        "scopes": ["people:read", "people:write"],  # sorted
    }


def test_self_returns_sorted_scopes(client, adapter):
    plaintext = _issue(adapter, "bot", ["identifiers:write", "dev:spoof", "people:read"])
    resp = client.get("/api-keys/self", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200
    assert resp.json()["scopes"] == sorted(["identifiers:write", "dev:spoof", "people:read"])


def test_self_works_for_env_bootstrap_key(client):
    resp = client.get("/api-keys/self", headers={"X-API-Key": "env-bootstrap-key-value"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "env-bootstrap"
    assert "admin" in body["scopes"]


def test_self_401_without_key(client):
    resp = client.get("/api-keys/self")
    assert resp.status_code == 401


def test_self_requires_no_specific_scope(client, adapter):
    """A key with zero scopes can still call /api-keys/self."""
    plaintext = _issue(adapter, "scopeless", [])
    resp = client.get("/api-keys/self", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200
    assert resp.json() == {"name": "scopeless", "scopes": []}


def test_self_403_for_dev_spoof_key_against_production(client, adapter, monkeypatch):
    """Guard applies to /api-keys/self too — it goes through require_api_key."""
    monkeypatch.setenv("TT_ENV", "production")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        plaintext = _issue(adapter, "playground", ["dev:spoof"])
        resp = client.get("/api-keys/self", headers={"X-API-Key": plaintext})
        assert resp.status_code == 403
    finally:
        get_settings.cache_clear()


def test_self_response_declared_in_openapi_schema(client):
    """The endpoint has a typed response model, so downstream code-gen sees the shape."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    self_op = schema["paths"]["/api-keys/self"]["get"]
    ref = self_op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/SelfKey")
    model = schema["components"]["schemas"]["SelfKey"]
    assert set(model["properties"]) == {"name", "scopes"}
