from contracts.directory import DirectoryClient, DirectoryUnavailable
from contracts.fetcher import Fetcher, FetchError, FetchResult
from contracts.storage import StorageAdapter


def test_fetchresult_holds_title_and_snapshot():
    r = FetchResult(title="Hi", content_snapshot="body")
    assert r.title == "Hi"


def test_exceptions_exist():
    assert issubclass(FetchError, Exception)
    assert issubclass(DirectoryUnavailable, Exception)


def test_protocols_importable():
    assert StorageAdapter is not None
    assert Fetcher is not None
    assert DirectoryClient is not None
