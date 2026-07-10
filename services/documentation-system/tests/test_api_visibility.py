from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from contracts.types import Source
from src.api.app import create_app
from src.api.deps import get_directory, get_fetchers, get_storage
from src.api.hashing import generate_key
from src.storage.in_memory import InMemoryStorageAdapter

ADMIN = {"X-API-Key": "test-key"}
P1 = "11111111-1111-1111-1111-111111111111"


def _sources():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Source(id="web", label="Web", url_patterns=[], requires_auth=False,
                   has_api=False, content_fetch_enabled=True,
                   created_at=now, updated_at=now, created_by="system", updated_by="system")]


class FakeFetchers:
    def fetch_for(self, source_id, url):
        from contracts.fetcher import FetchResult
        return FetchResult(title="Fetched", content_snapshot="body")


class FakeDirectory:
    def __init__(self, teams=frozenset()):
        self._teams = teams
    def get_team_label(self, team_id): return "T"
    def get_person_label(self, person_id): return "P"
    def get_active_team_ids(self, person_id): return self._teams


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    from src.config import get_settings
    get_settings.cache_clear()
    adapter = InMemoryStorageAdapter(seed_sources=_sources())
    app = create_app()
    app.dependency_overrides[get_storage] = lambda: adapter
    app.dependency_overrides[get_fetchers] = lambda: FakeFetchers()
    app.dependency_overrides[get_directory] = lambda: FakeDirectory()
    client = TestClient(app)

    def mk_key(scopes):
        plaintext, prefix, key_hash = generate_key()
        adapter.create_api_key(name=f"k-{prefix}", prefix=prefix, key_hash=key_hash, scopes=scopes, actor="t")
        return {"X-API-Key": plaintext}

    return client, adapter, mk_key


def test_actor_sees_only_person_granted_doc(ctx):
    client, adapter, mk_key = ctx
    # two docs via admin
    a = client.post("/docs", json={"url": "https://granted"}, headers=ADMIN).json()["doc"]["id"]
    client.post("/docs", json={"url": "https://hidden"}, headers=ADMIN)
    client.post(f"/docs/{a}/grants", json={"grantee_type": "person", "grantee_id": P1}, headers=ADMIN)

    reader = mk_key(["docs:read", "act-as-user"])
    obo = {**reader, "X-On-Behalf-Of": P1}
    listed = client.get("/docs", headers=obo).json()
    assert [d["url"] for d in listed] == ["https://granted"]
    assert client.get(f"/docs/{a}", headers=obo).status_code == 200


def test_no_actor_plain_read_key_sees_nothing(ctx):
    client, adapter, mk_key = ctx
    client.post("/docs", json={"url": "https://x"}, headers=ADMIN)
    reader = mk_key(["docs:read"])
    assert client.get("/docs", headers=reader).json() == []


def test_read_all_key_sees_everything(ctx):
    client, adapter, mk_key = ctx
    client.post("/docs", json={"url": "https://x"}, headers=ADMIN)
    reader = mk_key(["docs:read:all"])
    assert len(client.get("/docs", headers=reader).json()) == 1
