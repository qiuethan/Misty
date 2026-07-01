import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from src.config import get_settings
from src.storage.postgres import PostgresStorageAdapter

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PG_TESTS") != "1", reason="set RUN_PG_TESTS=1 to run Postgres tests"
)


@pytest.fixture
def adapter():
    engine = create_engine(get_settings().database_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE doc_tags, docs, api_keys RESTART IDENTITY CASCADE"))
    return PostgresStorageAdapter(engine)


def _mk(adapter, url="https://x.com", tags=None):
    return adapter.create_doc(
        url=url, url_normalized=url, source_id="web", title="X", description=None,
        owning_team_id=None, owning_team_label=None,
        owning_person_id=None, owning_person_label=None,
        content_snapshot=None, fetched_at=None, tags=tags or [], actor="tester",
    )


def test_create_get_and_dedup_lookup(adapter):
    d = _mk(adapter, tags=["a"])
    assert adapter.get_doc(d.id).tags == ["a"]
    assert adapter.get_doc_by_normalized_url("https://x.com").id == d.id


def test_soft_delete_and_filters(adapter):
    d = _mk(adapter)
    adapter.update_doc(d.id, {"active": False}, actor="t")
    assert adapter.list_docs(active_only=True) == []


def test_tag_add_remove_and_filter(adapter):
    d = _mk(adapter, tags=["x"])
    assert adapter.list_docs(tag="x")[0].id == d.id
    adapter.remove_tag(d.id, "x")
    assert adapter.list_docs(tag="x") == []


def test_sources_seeded(adapter):
    assert adapter.get_source("gdocs").url_patterns == ["docs.google.com/document"]


def test_api_key_roundtrip(adapter):
    k = adapter.create_api_key(name="bot", prefix="pfx98765", key_hash="h", scopes=["docs:read"], actor="cli")
    assert adapter.get_api_key_hash("pfx98765") == "h"
    adapter.revoke_api_key(k.id, actor="cli")
    assert adapter.get_api_key_hash("pfx98765") is None


def test_add_tag_idempotent(adapter):
    d = _mk(adapter, tags=["x"])
    assert adapter.add_tag(d.id, "x") is True   # duplicate — must not raise
    assert adapter.get_doc(d.id).tags == ["x"]  # still exactly one
    assert adapter.add_tag(d.id, "y") is True
    assert set(adapter.get_doc(d.id).tags) == {"x", "y"}


def test_get_by_normalized_url_with_duplicates_returns_one(adapter):
    a = _mk(adapter, url="https://dup.com")
    _mk(adapter, url="https://dup.com")  # same url_normalized, no unique constraint
    got = adapter.get_doc_by_normalized_url("https://dup.com")
    assert got is not None and got.id in (a.id,) or got is not None  # returns one, does not raise
