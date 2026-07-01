"""Tests for the API-key auth dependency.

Covers correct key, wrong key (same length), wrong key (different length),
empty key, missing key. All should return 401 without leaking timing info
or crashing on edge cases.
"""

import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.storage.in_memory import InMemoryStorageAdapter


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "correct-key-value")
    from src.config import get_settings

    get_settings.cache_clear()

    adapter = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def test_correct_key_returns_200(client):
    resp = client.get("/role_kinds", headers={"X-API-Key": "correct-key-value"})
    assert resp.status_code == 200


def test_wrong_key_same_length_returns_401(client):
    resp = client.get("/role_kinds", headers={"X-API-Key": "wrong-key-value--"})
    assert resp.status_code == 401


def test_wrong_key_different_length_returns_401(client):
    """Regression: compare_digest must handle differing lengths without crashing."""
    resp = client.get("/role_kinds", headers={"X-API-Key": "x"})
    assert resp.status_code == 401


def test_empty_key_returns_401(client):
    resp = client.get("/role_kinds", headers={"X-API-Key": ""})
    assert resp.status_code == 401


def test_missing_key_returns_401(client):
    resp = client.get("/role_kinds")
    assert resp.status_code == 401


def test_wrong_key_prefix_returns_401(client):
    """Prefix-matches must fail — this is what constant-time comparison prevents leaking."""
    resp = client.get("/role_kinds", headers={"X-API-Key": "correct-key-val"})
    assert resp.status_code == 401
