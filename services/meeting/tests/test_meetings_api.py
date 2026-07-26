"""Tests for the meeting HTTP + WebSocket endpoints, using a fake SessionRegistry
(no real ffmpeg/AWS/network) injected via app.dependency_overrides."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.deps import get_key_store
from src.api.hashing import generate_key
from src.api.wiring import get_session_registry
from src.contracts import Minutes, Segment, StopResponse
from src.key_store import InMemoryKeyStore


class FakeSession:
    def __init__(self, session_id, guild_id):
        self.session_id = session_id
        self.guild_id = guild_id
        self.feed_calls: list[tuple[str, str, bytes, int]] = []
        self.stop_called = False
        self._segments = [Segment(speaker="alice", start_ms=0, text="hello")]

    def feed(self, speaker_id, display_name, opus_payload, ts_ms):
        self.feed_calls.append((speaker_id, display_name, opus_payload, ts_ms))

    async def transcript_view(self):
        return self._segments

    async def stop(self):
        self.stop_called = True
        return StopResponse(
            transcript="[00:00] alice: hello",
            minutes=Minutes(summary="s", decisions=[], action_items=[]),
            pdf_b64="ZmFrZQ==",
            audio_b64=None,
        )


class FakeRegistry:
    def __init__(self):
        self.sessions: dict[str, FakeSession] = {}
        self.created_with: list[tuple[str, str]] = []

    def create(self, session_id, guild_id):
        session = FakeSession(session_id, guild_id)
        self.sessions[session_id] = session
        self.created_with.append((session_id, guild_id))
        return session

    def get(self, session_id):
        return self.sessions.get(session_id)


@pytest.fixture
def store():
    return InMemoryKeyStore()


@pytest.fixture
def consumer_key(store):
    plaintext, prefix, key_hash = generate_key()
    store.add(prefix=prefix, key_hash=key_hash, name="bot", scopes=["meetings"])
    return plaintext


@pytest.fixture
def registry():
    return FakeRegistry()


@pytest.fixture
def client(store, registry, monkeypatch):
    monkeypatch.setenv("API_KEY", "test-bootstrap-key")
    from src.config import get_settings

    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[get_key_store] = lambda: store
    app.dependency_overrides[get_session_registry] = lambda: registry
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_transcript_returns_fake_segments(client, registry, consumer_key):
    registry.create("s1", "g1")

    resp = client.get("/meetings/s1/transcript", headers={"X-API-Key": consumer_key})

    assert resp.status_code == 200
    body = resp.json()
    assert body["segments"] == [{"speaker": "alice", "start_ms": 0, "text": "hello"}]


def test_get_transcript_requires_key(client, registry):
    registry.create("s1", "g1")

    resp = client.get("/meetings/s1/transcript")

    assert resp.status_code == 401


def test_get_transcript_unknown_session_404(client, consumer_key):
    resp = client.get("/meetings/nope/transcript", headers={"X-API-Key": consumer_key})
    assert resp.status_code == 404


def test_get_transcript_invalid_session_id_400(client, consumer_key):
    resp = client.get(
        "/meetings/bad!id/transcript", headers={"X-API-Key": consumer_key}
    )
    assert resp.status_code == 400


def test_post_stop_returns_fake_stop_response(client, registry, consumer_key):
    session = registry.create("s1", "g1")

    resp = client.post("/meetings/s1/stop", headers={"X-API-Key": consumer_key})

    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "[00:00] alice: hello"
    assert body["minutes"]["summary"] == "s"
    assert session.stop_called is True


def test_post_stop_requires_key(client, registry):
    registry.create("s1", "g1")

    resp = client.post("/meetings/s1/stop")

    assert resp.status_code == 401


def test_post_stop_unknown_session_404(client, consumer_key):
    resp = client.post("/meetings/nope/stop", headers={"X-API-Key": consumer_key})
    assert resp.status_code == 404


def _frame(speaker_id: str, ts_ms: int, opus_payload: bytes) -> bytes:
    speaker_bytes = speaker_id.encode("utf-8")
    return (
        len(speaker_bytes).to_bytes(2, "big")
        + speaker_bytes
        + ts_ms.to_bytes(8, "big")
        + opus_payload
    )


def test_ws_stream_rejects_bad_key(client, registry):
    with pytest.raises(Exception):
        with client.websocket_connect("/meetings/s1/stream?key=wrong-key&guild_id=g1"):
            pass
    assert "s1" not in registry.sessions


def test_ws_stream_authenticates_and_feeds_decoded_frames(client, registry, consumer_key):
    with client.websocket_connect(
        f"/meetings/ws-session-1/stream?key={consumer_key}&guild_id=guild-42"
    ) as ws:
        ws.send_text('{"speaker_id": "alice-id", "display_name": "Alice"}')
        ws.send_bytes(_frame("alice-id", 0, b"opus-frame-1"))
        ws.send_bytes(_frame("bob-id", 100, b"opus-frame-2"))

    assert registry.created_with == [("ws-session-1", "guild-42")]
    session = registry.sessions["ws-session-1"]
    assert session.feed_calls == [
        ("alice-id", "Alice", b"opus-frame-1", 0),
        ("bob-id", "bob-id", b"opus-frame-2", 100),
    ]
    # Disconnect without POST /stop -- the WS handler must tear the session down.
    assert session.stop_called is True


def test_ws_stream_invalid_session_id_closes(client, registry, consumer_key):
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/meetings/bad!id/stream?key={consumer_key}&guild_id=g1"
        ):
            pass
    assert "bad!id" not in registry.sessions
