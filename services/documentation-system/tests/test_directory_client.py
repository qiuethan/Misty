from uuid import uuid4

import httpx
import pytest

from contracts.directory import DirectoryUnavailable
from src.directory.http_client import HttpDirectoryClient


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_get_team_label_returns_label():
    def handler(request):
        assert request.headers["X-API-Key"] == "k"
        return httpx.Response(200, json={"id": str(uuid4()), "label": "Partnerships"})
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    assert dc.get_team_label(uuid4()) == "Partnerships"


def test_get_person_label_uses_display_name():
    def handler(request):
        return httpx.Response(200, json={"display_name": "Priya"})
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    assert dc.get_person_label(uuid4()) == "Priya"


def test_404_returns_none():
    def handler(request):
        return httpx.Response(404, json={"detail": "not found"})
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    assert dc.get_team_label(uuid4()) is None


def test_connection_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    with pytest.raises(DirectoryUnavailable):
        dc.get_team_label(uuid4())


def test_5xx_raises_unavailable():
    def handler(request):
        return httpx.Response(503)
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    with pytest.raises(DirectoryUnavailable):
        dc.get_person_label(uuid4())


def test_403_raises_unavailable():
    def handler(request):
        return httpx.Response(403, json={"detail": "forbidden"})
    dc = HttpDirectoryClient("http://dir", "k", client=_client(handler))
    with pytest.raises(DirectoryUnavailable):
        dc.get_team_label(uuid4())
