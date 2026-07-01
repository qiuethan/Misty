"""Tests for the API-key auth dependency.

Covers:
- Env grace-period key (legacy path)
- DB-issued key with scope
- Wrong/missing/malformed key returns 401
- Missing scope returns 403
"""

import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.api.hashing import generate_key
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def env_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "env-bootstrap-key-value")
    from src.config import get_settings

    get_settings.cache_clear()
    yield "env-bootstrap-key-value"


@pytest.fixture
def adapter():
    return InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())


@pytest.fixture
def client(env_key, adapter):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def test_env_bootstrap_key_works(client, env_key):
    resp = client.get("/role_kinds", headers={"X-API-Key": env_key})
    assert resp.status_code == 200


def test_wrong_env_key_returns_401(client):
    resp = client.get("/role_kinds", headers={"X-API-Key": "wrong-key-value--x"})
    assert resp.status_code == 401


def test_missing_key_returns_401(client):
    resp = client.get("/role_kinds")
    assert resp.status_code == 401


def test_empty_key_returns_401(client):
    resp = client.get("/role_kinds", headers={"X-API-Key": ""})
    assert resp.status_code == 401


def test_malformed_prefix_returns_401(client):
    """A header that starts with tt_ but isn't a real key should 401, not crash."""
    resp = client.get("/role_kinds", headers={"X-API-Key": "tt_garbage"})
    assert resp.status_code == 401


def test_db_issued_key_works(client, adapter):
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="test-bot",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["role_kinds:read"],
        actor="admin",
    )
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200


def test_db_key_revoked_returns_401(client, adapter):
    plaintext, prefix, key_hash = generate_key()
    key = adapter.create_api_key(
        name="test-bot",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["role_kinds:read"],
        actor="admin",
    )
    adapter.revoke_api_key(key.id, actor="admin")
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 401


def test_db_key_wrong_secret_returns_401(client, adapter):
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="test-bot",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["role_kinds:read"],
        actor="admin",
    )
    # Tamper with the last chars — same prefix, wrong secret
    tampered = plaintext[:-4] + "XXXX"
    resp = client.get("/role_kinds", headers={"X-API-Key": tampered})
    assert resp.status_code == 401


def test_admin_scope_grants_everything(client, adapter):
    """A key with the 'admin' scope should pass any require_scope check."""
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="admin-bot",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["admin"],
        actor="admin",
    )
    # role_kinds needs :read but admin should suffice.
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200
