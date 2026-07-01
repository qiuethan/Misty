from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from contracts.types import RoleKind
from src.api.app import create_app
from src.api.deps import get_storage
from src.storage.in_memory import InMemoryStorageAdapter


def _seed_role_kinds() -> list[RoleKind]:
    now = datetime.utcnow()
    return [
        RoleKind(
            id=rid, label=rlabel, description=None, active=True,
            created_at=now, updated_at=now,
            created_by="system", updated_by="system",
        )
        for rid, rlabel in [
            ("executive", "Executive"),
            ("director", "Director"),
            ("lead", "Lead"),
            ("member", "Member"),
        ]
    ]


AUTH = {"X-API-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from src.config import get_settings

    get_settings.cache_clear()

    adapter = InMemoryStorageAdapter(seed_role_kinds=_seed_role_kinds())
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def test_list_role_kinds(client):
    resp = client.get("/role_kinds", headers=AUTH)
    assert resp.status_code == 200
    ids = {rk["id"] for rk in resp.json()}
    assert ids == {"executive", "director", "lead", "member"}


def test_get_role_kind(client):
    resp = client.get("/role_kinds/lead", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["label"] == "Lead"


def test_get_role_kind_not_found(client):
    resp = client.get("/role_kinds/nonexistent", headers=AUTH)
    assert resp.status_code == 404


def test_role_kinds_require_api_key(client):
    resp = client.get("/role_kinds")
    assert resp.status_code == 401
