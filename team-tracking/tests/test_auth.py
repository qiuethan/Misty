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


# --- dev:spoof environment guard --------------------------------------------

import logging

from src.api.hashing import generate_key as _gen_key_for_spoof_tests


def _issue_key_with_scopes(adapter, name: str, scopes: list[str]) -> str:
    """Helper: create a DB API key with the given scopes and return the plaintext."""
    plaintext, prefix, key_hash = _gen_key_for_spoof_tests()
    adapter.create_api_key(
        name=name, prefix=prefix, key_hash=key_hash, scopes=scopes, actor="test"
    )
    return plaintext


@pytest.fixture
def prod_env(monkeypatch, env_key):
    """Env bootstrap AND TT_ENV=production."""
    monkeypatch.setenv("TT_ENV", "production")
    from src.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_dev_spoof_key_rejected_when_tt_env_production(client, adapter, prod_env):
    plaintext = _issue_key_with_scopes(
        adapter, "playground-key", ["people:read", "dev:spoof"]
    )
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 403
    assert "dev:spoof" in resp.json()["detail"]


def test_dev_spoof_key_allowed_when_tt_env_local(client, adapter):
    # No prod_env — default local
    plaintext = _issue_key_with_scopes(
        adapter, "playground-key", ["role_kinds:read", "dev:spoof"]
    )
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200


def test_non_dev_spoof_key_unaffected_in_production(client, adapter, prod_env):
    plaintext = _issue_key_with_scopes(
        adapter, "prod-key", ["role_kinds:read"]
    )
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 200


def test_admin_scope_does_not_bypass_dev_spoof_guard(client, adapter, prod_env):
    """An `admin` scope wildcards `require_scope`, but MUST NOT bypass this guard."""
    plaintext = _issue_key_with_scopes(
        adapter, "danger-key", ["admin", "dev:spoof"]
    )
    resp = client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert resp.status_code == 403


def test_dev_spoof_rejection_logs_warning(client, adapter, prod_env, caplog):
    plaintext = _issue_key_with_scopes(
        adapter, "playground-key", ["dev:spoof"]
    )
    with caplog.at_level(logging.WARNING, logger="team_tracking.audit"):
        client.get("/role_kinds", headers={"X-API-Key": plaintext})
    assert any(
        "dev:spoof" in rec.message and "production" in rec.message
        for rec in caplog.records
    )
