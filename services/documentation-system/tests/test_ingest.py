from datetime import datetime, timezone
from uuid import uuid4

import pytest

from contracts.directory import DirectoryUnavailable
from contracts.fetcher import FetchError, FetchResult
from contracts.types import DocIngest, Source
from src.ingest import BadReference, ingest_doc
from src.storage.in_memory import InMemoryStorageAdapter


def _sources():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def mk(sid, patterns, fetch_on, auth=False):
        return Source(id=sid, label=sid, url_patterns=patterns, requires_auth=auth,
                      has_api=False, content_fetch_enabled=fetch_on,
                      created_at=now, updated_at=now, created_by="system", updated_by="system")
    return [mk("web", [], True), mk("github", ["github.com"], True),
            mk("gdrive", ["drive.google.com"], False, auth=True)]


class FakeFetchers:
    def __init__(self, result=None, error=None):
        self._result, self._error = result, error
    def fetch_for(self, source_id, url):
        if self._error:
            raise self._error
        return self._result


class FakeDirectory:
    def __init__(self, team=None, person=None, unavailable=False):
        self._team, self._person, self._down = team, person, unavailable
    def get_team_label(self, team_id):
        if self._down:
            raise DirectoryUnavailable("down")
        return self._team
    def get_person_label(self, person_id):
        if self._down:
            raise DirectoryUnavailable("down")
        return self._person


@pytest.fixture
def store():
    return InMemoryStorageAdapter(seed_sources=_sources())


def test_ingest_happy_path_derives_source_and_fetches_title(store):
    fetchers = FakeFetchers(result=FetchResult(title="Repo", content_snapshot="body"))
    res = ingest_doc(DocIngest(url="https://github.com/a/b"), storage=store,
                     fetchers=fetchers, directory=FakeDirectory(), actor="bot")
    assert res.created is True
    assert res.doc.source_id == "github"
    assert res.doc.title == "Repo"
    assert res.warnings == []


def test_ingest_dedup_returns_existing_and_merges_tags(store):
    f = FakeFetchers(result=FetchResult(title="X"))
    first = ingest_doc(DocIngest(url="https://x.com/a", tags=["one"]), storage=store,
                       fetchers=f, directory=FakeDirectory(), actor="bot")
    second = ingest_doc(DocIngest(url="https://x.com/a/", tags=["two"]), storage=store,
                        fetchers=f, directory=FakeDirectory(), actor="bot")
    assert second.created is False
    assert second.doc.id == first.doc.id
    assert set(second.doc.tags) == {"one", "two"}


def test_ingest_fetch_failure_warns_and_falls_back_to_url(store):
    fetchers = FakeFetchers(error=FetchError("timeout"))
    res = ingest_doc(DocIngest(url="https://github.com/a/b"), storage=store,
                     fetchers=fetchers, directory=FakeDirectory(), actor="bot")
    assert res.created is True
    assert res.doc.title == "https://github.com/a/b"
    assert any("fetch" in w for w in res.warnings)


def test_ingest_auth_source_warns_no_snapshot(store):
    res = ingest_doc(DocIngest(url="https://drive.google.com/file/d/z"), storage=store,
                     fetchers=FakeFetchers(), directory=FakeDirectory(), actor="bot")
    assert res.doc.source_id == "gdrive"
    assert any("auth" in w for w in res.warnings)


def test_ingest_bad_team_id_when_directory_up_raises(store):
    with pytest.raises(BadReference):
        ingest_doc(DocIngest(url="https://x.com", owning_team_id=uuid4()), storage=store,
                   fetchers=FakeFetchers(result=FetchResult(title="X")),
                   directory=FakeDirectory(team=None), actor="bot")


def test_ingest_directory_down_warns_and_defers_label(store):
    res = ingest_doc(DocIngest(url="https://x.com", owning_team_id=uuid4()), storage=store,
                     fetchers=FakeFetchers(result=FetchResult(title="X")),
                     directory=FakeDirectory(unavailable=True), actor="bot")
    assert res.created is True
    assert res.doc.owning_team_label is None
    assert any("directory" in w.lower() for w in res.warnings)


def test_ingest_bad_source_id_raises(store):
    with pytest.raises(BadReference):
        ingest_doc(DocIngest(url="https://x.com", source_id="nope"), storage=store,
                   fetchers=FakeFetchers(), directory=FakeDirectory(), actor="bot")


def test_ingest_applies_grants(store):
    payload = DocIngest(url="https://g.com", grants=[{"grantee_type": "org"}])
    result = ingest_doc(payload, storage=store,
                        fetchers=FakeFetchers(result=FetchResult(title="G")),
                        directory=FakeDirectory(), actor="t")
    grants = store.list_grants(result.doc.id)
    assert [(g.grantee_type, g.grantee_id) for g in grants] == [("org", None)]


def test_ingest_dedup_applies_grants_to_existing_doc(store):
    f = FakeFetchers(result=FetchResult(title="X"))
    first = ingest_doc(DocIngest(url="https://x.com/a"), storage=store,
                       fetchers=f, directory=FakeDirectory(), actor="bot")
    second = ingest_doc(
        DocIngest(url="https://x.com/a/", grants=[{"grantee_type": "org"}]),
        storage=store, fetchers=f, directory=FakeDirectory(), actor="bot",
    )
    assert second.doc.id == first.doc.id
    grants = store.list_grants(first.doc.id)
    assert [(g.grantee_type, g.grantee_id) for g in grants] == [("org", None)]
