"""Tests for the structured audit log middleware."""

import json

import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.api.hashing import generate_key
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def env_setup(monkeypatch):
    monkeypatch.setenv("API_KEY", "env-test-key")
    from src.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def adapter():
    return InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())


@pytest.fixture
def client(env_setup, adapter):
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def _last_log_line(capsys) -> dict:
    """Grab the last non-empty JSON line from stdout capture."""
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip().startswith("{")]
    assert lines, "no audit log line emitted"
    return json.loads(lines[-1])


def test_log_line_shape_on_success(client, capsys):
    client.get("/role_kinds", headers={"X-API-Key": "env-test-key"})
    entry = _last_log_line(capsys)
    assert entry["method"] == "GET"
    assert entry["path"] == "/role_kinds"
    assert entry["status"] == 200
    assert entry["key_name"] == "env-bootstrap"
    assert entry["is_bootstrap"] is True
    assert "request_id" in entry
    assert "duration_ms" in entry
    assert "ts" in entry


def test_log_line_on_401(client, capsys):
    client.get("/role_kinds", headers={"X-API-Key": "wrong-key-value"})
    entry = _last_log_line(capsys)
    assert entry["status"] == 401
    assert entry["key_name"] is None
    assert entry["is_bootstrap"] is False


def test_log_line_key_name_for_db_key(client, adapter, capsys):
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="log-bot",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["role_kinds:read"],
        actor="admin",
    )
    client.get("/role_kinds", headers={"X-API-Key": plaintext})
    entry = _last_log_line(capsys)
    assert entry["key_name"] == "log-bot"
    assert entry["is_bootstrap"] is False


def test_log_line_on_403_scope_denial(client, adapter, capsys):
    plaintext, prefix, key_hash = generate_key()
    adapter.create_api_key(
        name="read-only",
        prefix=prefix,
        key_hash=key_hash,
        scopes=["role_kinds:read"],  # no people:write
        actor="admin",
    )
    resp = client.post(
        "/people",
        json={"display_name": "x", "primary_email": "x@utmist.ca"},
        headers={"X-API-Key": plaintext},
    )
    assert resp.status_code == 403
    entry = _last_log_line(capsys)
    assert entry["status"] == 403
    # Auth succeeded — key_name should be set even though scope failed
    assert entry["key_name"] == "read-only"


def test_log_line_respects_x_forwarded_for(client, capsys):
    client.get(
        "/role_kinds",
        headers={"X-API-Key": "env-test-key", "X-Forwarded-For": "203.0.113.7"},
    )
    entry = _last_log_line(capsys)
    assert entry["remote"] == "203.0.113.7"
