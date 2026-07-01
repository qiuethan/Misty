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


def test_create_and_get_team(client):
    resp = client.post("/teams", json={"slug": "ops", "label": "Ops"}, headers=AUTH)
    assert resp.status_code == 201
    body = resp.json()
    got = client.get(f"/teams/{body['id']}", headers=AUTH).json()
    assert got["slug"] == "ops"


def test_get_team_by_slug(client):
    client.post("/teams", json={"slug": "ops", "label": "Ops"}, headers=AUTH)
    resp = client.get("/teams/by-slug/ops", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["label"] == "Ops"


def test_team_hierarchy(client):
    parent = client.post(
        "/teams", json={"slug": "events", "label": "Events"}, headers=AUTH
    ).json()
    child_resp = client.post(
        "/teams",
        json={"slug": "events.agi", "label": "AGI", "parent_id": parent["id"]},
        headers=AUTH,
    )
    assert child_resp.status_code == 201
    assert child_resp.json()["parent_id"] == parent["id"]


def test_duplicate_slug_returns_409(client):
    client.post("/teams", json={"slug": "ops", "label": "Ops"}, headers=AUTH)
    dup = client.post("/teams", json={"slug": "ops", "label": "Other"}, headers=AUTH)
    assert dup.status_code == 409


def test_update_team(client):
    created = client.post(
        "/teams", json={"slug": "ops", "label": "Ops"}, headers=AUTH
    ).json()
    resp = client.patch(
        f"/teams/{created['id']}", json={"label": "Internal Ops"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.json()["label"] == "Internal Ops"


def test_create_team_requires_api_key(client):
    resp = client.post("/teams", json={"slug": "ops", "label": "Ops"})
    assert resp.status_code == 401


def test_get_team_by_slug_not_found(client):
    resp = client.get("/teams/by-slug/nonexistent", headers=AUTH)
    assert resp.status_code == 404
