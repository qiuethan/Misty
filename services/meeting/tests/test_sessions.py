"""Tests for the stateful session registry + meeting lifecycle, using fakes only
(no real ffmpeg/AWS/network)."""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone

import pytest

from src.contracts import Minutes
from src.sessions import SessionAlreadyExistsError, SessionRegistry, words_to_segments


class FakeAudio:
    """Pass-through 'decoder': in these tests the opus_frame_bytes IS the pcm payload,
    so we can assert routing without any real ffmpeg/opus decode."""

    def __init__(self):
        self.decode_calls = []

    def decode(self, opus_frame_bytes: bytes) -> bytes:
        self.decode_calls.append(opus_frame_bytes)
        return opus_frame_bytes


class FakeTranscriber:
    """Canned transcriber: returns a fixed word list regardless of input, but drains
    the pcm_chunks async iterable to prove the routing/buffering plumbing works."""

    def __init__(self, words):
        self._words = words
        self.calls = 0
        self.last_chunks = None

    async def transcribe(self, pcm_chunks, sample_rate=16000):
        chunks = [c async for c in pcm_chunks]
        self.last_chunks = chunks
        self.calls += 1
        return {"text": " ".join(w["text"] for w in self._words), "words": self._words}


class FakeMixer:
    def __init__(self, mp3_bytes=b"ID3-fake-mp3-bytes"):
        self._mp3_bytes = mp3_bytes
        self.calls = []

    def mix(self, input_paths, output_path):
        self.calls.append((list(input_paths), output_path))
        return self._mp3_bytes


def _fake_report_builder(segments, meta):
    minutes = Minutes(summary="Test summary", decisions=["d1"], action_items=["a1"])
    pdf_bytes = b"%PDF-1.4 fake pdf content for testing purposes only"
    return minutes, pdf_bytes


def _make_deps(tmp_root, transcribers_by_speaker, audio=None, mixer=None):
    queue = list(transcribers_by_speaker)

    def make_transcriber():
        return queue.pop(0)

    return {
        "make_transcriber": make_transcriber,
        "audio": audio or FakeAudio(),
        "mixer": mixer or FakeMixer(),
        "report_builder": _fake_report_builder,
        "tmp_root": tmp_root,
        "now": lambda: datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def tmp_root():
    d = tempfile.mkdtemp(prefix="meeting-sessions-test-")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_words_to_segments_splits_on_gap_over_3s():
    words = [
        {"text": "hi", "start_ms": 100},
        {"text": "friend", "start_ms": 4000},
    ]
    segments = words_to_segments("bob", words, gap_ms=3000)

    assert [(s.start_ms, s.text) for s in segments] == [(100, "hi"), (4000, "friend")]
    assert all(s.speaker == "bob" for s in segments)


def test_words_to_segments_keeps_close_words_in_one_segment():
    words = [
        {"text": "hello", "start_ms": 0},
        {"text": "there", "start_ms": 500},
    ]
    segments = words_to_segments("alice", words, gap_ms=3000)

    assert len(segments) == 1
    assert segments[0].start_ms == 0
    assert segments[0].text == "hello there"


def test_create_rejects_duplicate_session_id(tmp_root):
    registry = SessionRegistry(_make_deps(tmp_root, []))
    registry.create("s1", "g1")

    with pytest.raises(SessionAlreadyExistsError):
        registry.create("s1", "g1")


def test_feed_and_transcript_view_merge_chronologically_across_speakers(tmp_root):
    alice_words = [
        {"text": "hello", "start_ms": 0},
        {"text": "there", "start_ms": 500},
    ]
    bob_words = [
        {"text": "hi", "start_ms": 100},
        {"text": "friend", "start_ms": 4000},
    ]
    alice_transcriber = FakeTranscriber(alice_words)
    bob_transcriber = FakeTranscriber(bob_words)
    audio = FakeAudio()
    deps = _make_deps(tmp_root, [alice_transcriber, bob_transcriber], audio=audio)
    registry = SessionRegistry(deps)

    session = registry.create("session-1", "guild-1")
    session.feed("alice-id", "alice", b"alice-frame-1", ts_ms=0)
    session.feed("bob-id", "bob", b"bob-frame-1", ts_ms=100)
    session.feed("alice-id", "alice", b"alice-frame-2", ts_ms=500)

    # Routing: decode was called once per fed frame.
    assert audio.decode_calls == [b"alice-frame-1", b"bob-frame-1", b"alice-frame-2"]

    view = asyncio.run(session.transcript_view())

    assert [(s.speaker, s.start_ms, s.text) for s in view] == [
        ("alice", 0, "hello there"),
        ("bob", 100, "hi"),
        ("bob", 4000, "friend"),
    ]

    result = asyncio.run(session.stop())

    assert result.transcript == (
        "[00:00] alice: hello there\n[00:00] bob: hi\n[00:04] bob: friend"
    )
    assert result.minutes.summary == "Test summary"

    import base64

    assert base64.b64decode(result.pdf_b64)[:4] == b"%PDF"
    assert result.audio_b64 is not None
    assert base64.b64decode(result.audio_b64) == b"ID3-fake-mp3-bytes"

    # Cleanup: the session's temp dir must be removed, and it must be deregistered.
    session_tmp_dir = os.path.join(tmp_root, "session-1")
    assert not os.path.exists(session_tmp_dir)
    assert registry.get("session-1") is None
    # Re-creating the same id must now succeed (fully deregistered).
    registry.create("session-1", "guild-1")


def test_stop_skips_audio_when_no_tracks(tmp_root):
    deps = _make_deps(tmp_root, [])
    registry = SessionRegistry(deps)
    session = registry.create("session-empty", "guild-1")

    result = asyncio.run(session.stop())

    assert result.audio_b64 is None
    assert result.transcript == ""


def test_discard_cleans_up_without_running_finalize_pipeline(tmp_root):
    alice_words = [{"text": "hello", "start_ms": 0}]
    transcriber = FakeTranscriber(alice_words)
    audio = FakeAudio()
    mixer = FakeMixer()
    deps = _make_deps(tmp_root, [transcriber], audio=audio, mixer=mixer)
    registry = SessionRegistry(deps)

    session = registry.create("session-discard", "guild-1")
    session.feed("alice-id", "alice", b"alice-frame-1", ts_ms=0)

    session.discard()

    # Cleanup happened: tmp dir gone, deregistered from the registry.
    session_tmp_dir = os.path.join(tmp_root, "session-discard")
    assert not os.path.exists(session_tmp_dir)
    assert registry.get("session-discard") is None

    # The full finalize pipeline (transcribe/report_builder/mix) must NOT run.
    assert transcriber.calls == 0
    assert mixer.calls == []

    # Idempotent: calling discard() again must not raise.
    session.discard()

    # Re-creating the same id must now succeed (fully deregistered).
    registry.create("session-discard", "guild-1")


def test_stop_cleans_up_tmp_dir_even_on_report_builder_error(tmp_root):
    def boom(segments, meta):
        raise RuntimeError("report builder exploded")

    deps = _make_deps(tmp_root, [])
    deps["report_builder"] = boom
    registry = SessionRegistry(deps)
    session = registry.create("session-err", "guild-1")

    with pytest.raises(RuntimeError):
        asyncio.run(session.stop())

    assert not os.path.exists(os.path.join(tmp_root, "session-err"))
    assert registry.get("session-err") is None
