from datetime import datetime, timezone

import pytest

from contracts.types import Source
from src.storage.in_memory import InMemoryStorageAdapter


def _sources():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Source(id="web", label="Web", url_patterns=[], requires_auth=False,
               has_api=False, content_fetch_enabled=True,
               created_at=now, updated_at=now, created_by="system", updated_by="system"),
    ]


@pytest.fixture
def store():
    return InMemoryStorageAdapter(seed_sources=_sources())


def _mk(store, url="https://x.com", tags=None):
    return store.create_doc(
        url=url, url_normalized=url, source_id="web", title="X", description=None,
        owning_team_id=None, owning_team_label=None,
        owning_person_id=None, owning_person_label=None,
        content_snapshot=None, fetched_at=None, tags=tags or [], actor="tester",
    )


def test_create_and_get_doc(store):
    d = _mk(store)
    assert store.get_doc(d.id).url == "https://x.com"
    assert d.created_by == "tester"


def test_get_by_normalized_url(store):
    _mk(store, url="https://x.com")
    assert store.get_doc_by_normalized_url("https://x.com") is not None
    assert store.get_doc_by_normalized_url("https://nope.com") is None


def test_tags_roundtrip_and_dedup(store):
    d = _mk(store, tags=["a", "b"])
    assert set(store.get_doc(d.id).tags) == {"a", "b"}
    assert store.add_tag(d.id, "a") is True  # idempotent
    assert set(store.get_doc(d.id).tags) == {"a", "b"}
    store.add_tag(d.id, "c")
    assert "c" in store.get_doc(d.id).tags
    assert store.remove_tag(d.id, "a") is True
    assert "a" not in store.get_doc(d.id).tags


def test_soft_delete_and_active_only_filter(store):
    d = _mk(store)
    store.update_doc(d.id, {"active": False}, actor="tester")
    assert store.list_docs(active_only=True) == []
    assert len(store.list_docs(active_only=False)) == 1


def test_list_filters_by_tag_and_source(store):
    a = _mk(store, url="https://a.com", tags=["x"])
    _mk(store, url="https://b.com", tags=["y"])
    got = store.list_docs(tag="x")
    assert [d.id for d in got] == [a.id]


def test_api_key_lifecycle(store):
    k = store.create_api_key(name="bot", prefix="pfx12345", key_hash="h", scopes=["docs:read"], actor="cli")
    assert store.get_api_key_hash("pfx12345") == "h"
    store.revoke_api_key(k.id, actor="cli")
    assert store.get_api_key_hash("pfx12345") is None
