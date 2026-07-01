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


def test_openapi_lists_all_expected_paths(client):
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"].keys())
    expected = {
        "/people",
        "/people/{person_id}",
        "/teams",
        "/teams/{team_id}",
        "/teams/by-slug/{slug}",
        "/role_kinds",
        "/role_kinds/{role_kind_id}",
        "/memberships",
        "/memberships/{membership_id}",
        "/memberships/{membership_id}/end",
    }
    missing = expected - paths
    assert not missing, f"missing paths in OpenAPI: {missing}"


def test_openapi_documents_person_shape(client):
    schema = client.get("/openapi.json").json()
    person = schema["components"]["schemas"]["Person"]
    props = person["properties"]
    for field in (
        "id",
        "display_name",
        "primary_email",
        "active",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ):
        assert field in props, f"Person missing field {field}"


def test_openapi_has_title_and_version(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "UTMIST team-tracking"
    assert schema["info"]["version"] == "0.1.0"


def test_openapi_tags_present(client):
    schema = client.get("/openapi.json").json()
    tags_used = {
        tag for path in schema["paths"].values() for op in path.values() for tag in op.get("tags", [])
    }
    assert tags_used >= {"people", "teams", "role_kinds", "memberships"}
