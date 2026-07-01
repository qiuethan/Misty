from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import build_seed_role_kinds
from src.api.app import create_app
from src.api.deps import get_storage
from src.storage.in_memory import InMemoryStorageAdapter

AUTH = {"X-API-Key": "test-key"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from src.config import get_settings

    get_settings.cache_clear()

    adapter = InMemoryStorageAdapter(seed_role_kinds=build_seed_role_kinds())
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    with TestClient(app) as c:
        yield c


def _create_person_and_team(client):
    p = client.post(
        "/people",
        json={"display_name": "Alex", "primary_email": "alex@utmist.ca"},
        headers=AUTH,
    ).json()
    t = client.post("/teams", json={"slug": "ops", "label": "Ops"}, headers=AUTH).json()
    return p, t


def test_create_membership_defaults_to_member(client):
    p, t = _create_person_and_team(client)
    resp = client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"]},
        headers=AUTH,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role_kind_id"] == "member"
    assert body["is_team_admin"] is False
    assert body["ended_at"] is None


def test_create_membership_with_admin_flag(client):
    p, t = _create_person_and_team(client)
    resp = client.post(
        "/memberships",
        json={
            "person_id": p["id"],
            "team_id": t["id"],
            "role_kind_id": "lead",
            "is_team_admin": True,
        },
        headers=AUTH,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role_kind_id"] == "lead"
    assert body["is_team_admin"] is True


def test_list_memberships_by_team(client):
    p, t = _create_person_and_team(client)
    client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"]},
        headers=AUTH,
    )
    resp = client.get(f"/memberships?team_id={t['id']}", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_memberships_active_only(client):
    p, t = _create_person_and_team(client)
    m = client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"]},
        headers=AUTH,
    ).json()
    client.post(
        f"/memberships/{m['id']}/end",
        json={"ended_at": str(date.today())},
        headers=AUTH,
    )
    assert len(client.get("/memberships", headers=AUTH).json()) == 1
    assert len(client.get("/memberships?active_only=true", headers=AUTH).json()) == 0


def test_end_membership(client):
    p, t = _create_person_and_team(client)
    m = client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"]},
        headers=AUTH,
    ).json()
    end = str(date(2027, 4, 30))
    resp = client.post(
        f"/memberships/{m['id']}/end",
        json={"ended_at": end},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["ended_at"] == end


def test_update_membership_admin_flag(client):
    p, t = _create_person_and_team(client)
    m = client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"]},
        headers=AUTH,
    ).json()
    resp = client.patch(
        f"/memberships/{m['id']}",
        json={"is_team_admin": True},
        headers=AUTH,
    )
    assert resp.status_code == 200
    assert resp.json()["is_team_admin"] is True


def test_as_of_query(client):
    p, t = _create_person_and_team(client)
    client.post(
        "/memberships",
        json={
            "person_id": p["id"],
            "team_id": t["id"],
            "started_at": "2024-09-01",
            "ended_at": "2025-04-30",
        },
        headers=AUTH,
    )
    r_during = client.get("/memberships?as_of=2025-01-15", headers=AUTH).json()
    r_after = client.get("/memberships?as_of=2025-06-01", headers=AUTH).json()
    assert len(r_during) == 1
    assert len(r_after) == 0


def test_filter_by_team_admin(client):
    p, t = _create_person_and_team(client)
    client.post(
        "/memberships",
        json={"person_id": p["id"], "team_id": t["id"], "is_team_admin": True},
        headers=AUTH,
    )
    p2 = client.post(
        "/people",
        json={"display_name": "B", "primary_email": "b@utmist.ca"},
        headers=AUTH,
    ).json()
    client.post(
        "/memberships",
        json={"person_id": p2["id"], "team_id": t["id"]},
        headers=AUTH,
    )
    admins = client.get(
        f"/memberships?team_id={t['id']}&is_team_admin=true",
        headers=AUTH,
    ).json()
    non_admins = client.get(
        f"/memberships?team_id={t['id']}&is_team_admin=false",
        headers=AUTH,
    ).json()
    assert len(admins) == 1
    assert len(non_admins) == 1


def test_create_membership_fk_missing_returns_400(client):
    """Bad person/team FK yields 400, not 500."""
    resp = client.post(
        "/memberships",
        json={
            "person_id": "00000000-0000-0000-0000-000000000000",
            "team_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=AUTH,
    )
    assert resp.status_code == 400


def test_end_nonexistent_membership_returns_404(client):
    resp = client.post(
        "/memberships/00000000-0000-0000-0000-000000000000/end",
        json={"ended_at": str(date.today())},
        headers=AUTH,
    )
    assert resp.status_code == 404
