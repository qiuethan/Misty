"""Tests for the stateful session registry + meeting lifecycle, using fakes only
(no real ffmpeg/AWS/network)."""

import asyncio
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone

import pytest

from src.contracts import Minutes
from src.sessions import SessionAlreadyExistsError, SessionRegistry, words_to_segments


class _FakeDecoder:
    """Pass-through per-speaker 'decoder': in these tests the opus_frame_bytes
    IS the pcm payload, so we can assert routing without any real Opus decode.
    Records into the FakeAudio-shared ``decode_calls`` list so tests can
    assert call order across speakers (each speaker gets its OWN instance, as
    make_decoder() is a factory, but they all log to the same list)."""

    def __init__(self, decode_calls: list[bytes]):
        self._decode_calls = decode_calls

    def decode(self, opus_frame_bytes: bytes) -> bytes:
        self._decode_calls.append(opus_frame_bytes)
        return opus_frame_bytes


class FakeAudio:
    """Factory for per-speaker fake decoders (mirrors the real
    ``AudioAdapter.make_decoder()`` contract)."""

    def __init__(self):
        self.decode_calls = []

    def make_decoder(self) -> _FakeDecoder:
        return _FakeDecoder(self.decode_calls)


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


def _make_deps(tmp_root, transcribers_by_speaker, audio=None, mixer=None, now=None):
    queue = list(transcribers_by_speaker)

    def make_transcriber():
        return queue.pop(0)

    return {
        "make_transcriber": make_transcriber,
        "audio": audio or FakeAudio(),
        "mixer": mixer or FakeMixer(),
        "report_builder": _fake_report_builder,
        "tmp_root": tmp_root,
        "now": now or (lambda: datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)),
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
    # Both speakers' Transcribe output starts near 0 -- this is realistic: AWS
    # Transcribe's word start_ms is relative to the start of each speaker's OWN
    # concatenated PCM buffer, not to the meeting. Bob's FIRST fed frame has
    # ts_ms=30000 (he starts speaking ~30s into the meeting), even though his
    # own Transcribe words start at ~0/100 relative to his own buffer. The
    # session must anchor bob's words to his base ts_ms so the merged,
    # cross-speaker transcript sorts him AFTER alice, not before.
    alice_words = [
        {"text": "hello", "start_ms": 0},
        {"text": "there", "start_ms": 500},
    ]
    bob_words = [
        {"text": "hi", "start_ms": 0},
        {"text": "friend", "start_ms": 100},
    ]
    alice_transcriber = FakeTranscriber(alice_words)
    bob_transcriber = FakeTranscriber(bob_words)
    audio = FakeAudio()
    deps = _make_deps(tmp_root, [alice_transcriber, bob_transcriber], audio=audio)
    registry = SessionRegistry(deps)

    session = registry.create("session-1", "guild-1")
    session.feed("alice-id", "alice", b"alice-frame-1", ts_ms=0)
    session.feed("bob-id", "bob", b"bob-frame-1", ts_ms=30000)
    session.feed("alice-id", "alice", b"alice-frame-2", ts_ms=500)
    session.feed("bob-id", "bob", b"bob-frame-2", ts_ms=30100)

    # Routing: decode was called once per fed frame.
    assert audio.decode_calls == [
        b"alice-frame-1",
        b"bob-frame-1",
        b"alice-frame-2",
        b"bob-frame-2",
    ]

    view = asyncio.run(session.transcript_view())

    # Bob's words, anchored to his base ts_ms (30000), must sort AFTER alice's,
    # even though Bob's raw Transcribe start_ms values (0, 100) are smaller
    # than alice's (0, 500) in isolation.
    assert [(s.speaker, s.start_ms, s.text) for s in view] == [
        ("alice", 0, "hello there"),
        ("bob", 30000, "hi friend"),
    ]

    result = asyncio.run(session.stop())

    assert result.transcript == ("[00:00] alice: hello there\n[00:30] bob: hi friend")
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


def test_stop_meta_duration_label_reflects_elapsed_time(tmp_root):
    # Fix #8: duration_label must be computed from started_at -> now, not left
    # empty.
    clock = {"t": datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)}

    def now():
        return clock["t"]

    captured_meta = {}

    def capturing_report_builder(segments, meta):
        captured_meta.update(meta)
        return Minutes(summary="s", decisions=[], action_items=[]), b"%PDF-fake"

    deps = _make_deps(tmp_root, [], now=now)
    deps["report_builder"] = capturing_report_builder
    registry = SessionRegistry(deps)
    session = registry.create("session-duration", "guild-1")

    # Advance the clock by 5 minutes 30 seconds before stop().
    clock["t"] = datetime(2026, 7, 25, 18, 5, 30, tzinfo=timezone.utc)
    asyncio.run(session.stop())

    assert captured_meta["duration_label"] == "5m"


def test_feed_drops_frames_and_logs_once_past_max_meeting_ms(tmp_root):
    # Fix #4: once elapsed time exceeds max_meeting_ms, further frames are
    # dropped (not buffered) to bound unbounded PCM growth. This does NOT fix
    # the separate transcript_view()/stop() re-billing issue (deferred to
    # sub-plan 3) -- it only bounds memory/duration.
    clock = {"t": datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)}

    def now():
        return clock["t"]

    audio = FakeAudio()
    transcriber = FakeTranscriber([])
    deps = _make_deps(tmp_root, [transcriber], audio=audio, now=now)
    deps["max_meeting_ms"] = 60_000  # 1 minute cap
    registry = SessionRegistry(deps)
    session = registry.create("session-cap", "guild-1")

    session.feed("alice-id", "alice", b"frame-within-cap", ts_ms=0)
    assert len(audio.decode_calls) == 1

    # Advance well past the cap.
    clock["t"] = datetime(2026, 7, 25, 18, 2, 0, tzinfo=timezone.utc)
    session.feed("alice-id", "alice", b"frame-past-cap", ts_ms=120_000)

    # The past-cap frame was dropped: no additional decode call, and the
    # buffer only contains the earlier, within-cap frame.
    assert len(audio.decode_calls) == 1
    buf = session._speakers["alice-id"]
    assert buf.pcm_chunks == [b"frame-within-cap"]


def test_feed_does_not_drop_frames_when_max_meeting_ms_is_none(tmp_root):
    # With no cap (the default -- max_meeting_ms absent/None), a meeting runs
    # indefinitely: frames are buffered no matter how much time has elapsed,
    # well past the OLD 4h default.
    clock = {"t": datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)}

    def now():
        return clock["t"]

    audio = FakeAudio()
    # One speaker ("alice-id") -> one transcriber created on her first frame.
    deps = _make_deps(tmp_root, [FakeTranscriber([])], audio=audio, now=now)
    assert deps.get("max_meeting_ms") is None  # no cap by default
    registry = SessionRegistry(deps)
    session = registry.create("session-nocap", "guild-1")

    session.feed("alice-id", "alice", b"frame-1", ts_ms=0)

    # Advance the clock 12 hours -- far beyond the old 4h cap.
    clock["t"] = datetime(2026, 7, 26, 6, 0, tzinfo=timezone.utc)
    session.feed("alice-id", "alice", b"frame-2", ts_ms=43_200_000)

    # Both frames were buffered: nothing dropped.
    assert len(audio.decode_calls) == 2
    buf = session._speakers["alice-id"]
    assert buf.pcm_chunks == [b"frame-1", b"frame-2"]


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


def test_feed_sanitizes_path_traversal_speaker_id(tmp_root):
    """A malicious speaker_id (attacker/caller-controlled, decoded straight off
    the WS binary frame with no validation upstream -- see
    api/routers/meetings.py) must never let feed() write outside the
    session's own tmp dir, and the sanitized on-disk filename must contain no
    path separators."""
    audio = FakeAudio()
    malicious_ids = ["../../etc/evil", "/abs/path/evil", "../../../../tmp/pwned"]
    transcribers = [FakeTranscriber([]) for _ in malicious_ids]
    deps = _make_deps(tmp_root, transcribers, audio=audio)
    registry = SessionRegistry(deps)
    session = registry.create("session-traversal", "guild-1")

    for speaker_id in malicious_ids:
        session.feed(speaker_id, "display", b"frame", ts_ms=0)

    session_tmp_dir = os.path.realpath(os.path.join(tmp_root, "session-traversal"))
    for speaker_id in malicious_ids:
        buf = session._speakers[speaker_id]
        # The written file must stay under the session's own tmp dir.
        real_path = os.path.realpath(buf.pcm_path)
        assert real_path.startswith(session_tmp_dir + os.sep)
        # The filename component itself must contain no path separators.
        filename = os.path.basename(buf.pcm_path)
        assert os.sep not in filename
        assert "/" not in filename and ".." not in filename
        assert os.path.exists(buf.pcm_path)

    # Distinct raw ids must not collide onto the same sanitized filename.
    filenames = {os.path.basename(session._speakers[sid].pcm_path) for sid in malicious_ids}
    assert len(filenames) == len(malicious_ids)

    # display_name / speaker label plumbing is untouched: raw speaker_id
    # remains the dict key and is unaffected by path sanitization.
    assert set(session._speakers.keys()) == set(malicious_ids)


def test_transcript_view_tolerates_new_speaker_added_during_iteration(tmp_root):
    """Regression for 'dictionary changed size during iteration': feed() runs
    synchronously (e.g. from the live WS ingest loop) and can insert a
    brand-new speaker into self._speakers while transcript_view() is
    suspended at an `await` mid-iteration over the existing speakers. The
    view must snapshot before iterating so this doesn't crash, and a speaker
    added mid-poll is simply picked up on a later call."""

    class InsertingTranscriber:
        """A fake transcriber whose transcribe() call simulates a concurrent
        feed() for a brand-new speaker arriving mid-iteration (as would happen
        if the live WS ingest loop ran on another asyncio task while this
        coroutine was suspended at `await`)."""

        def __init__(self, session):
            self._session = session
            self._did_insert = False

        async def transcribe(self, pcm_chunks, sample_rate=16000):
            _ = [c async for c in pcm_chunks]
            if not self._did_insert:
                self._did_insert = True
                self._session.feed("late-speaker", "late", b"late-frame", ts_ms=0)
            return {"text": "hi", "words": [{"text": "hi", "start_ms": 0}]}

    audio = FakeAudio()
    deps = _make_deps(tmp_root, [], audio=audio)
    registry = SessionRegistry(deps)
    session = registry.create("session-mutate", "guild-1")

    # Install a transcriber for "alice-id" that mutates self._speakers when
    # awaited -- reproducing the "insert during await" race feed() enables.
    session._deps["make_transcriber"] = lambda: InsertingTranscriber(session)
    session.feed("alice-id", "alice", b"alice-frame", ts_ms=0)

    # Must not raise "RuntimeError: dictionary changed size during iteration".
    view = asyncio.run(session.transcript_view())

    # Only alice's words show up in THIS poll's view (the late speaker's
    # buffer had no words fed into their own transcriber run this pass) --
    # they'll appear on a subsequent poll instead. The key assertion is that
    # iteration didn't crash, and the new speaker IS now tracked.
    assert [(s.speaker, s.text) for s in view] == [("alice", "hi")]
    assert "late-speaker" in session._speakers


def test_feed_from_worker_thread_races_readers_without_crashing(tmp_root):
    """Regression for the thread-safety follow-up: feed() runs on a WORKER
    THREAD in production (asyncio.to_thread from the WS ingest loop) while
    _meta()/stop()'s pcm_paths comprehension run on the event-loop thread.
    Both iterate self._speakers.values() directly (not via `list(...)` at the
    call site), so without a lock a comprehension can observe the dict
    resizing mid-iteration and raise "RuntimeError: dictionary changed size
    during iteration". Hammer feed() from real background threads while
    repeatedly calling _meta() and building pcm_paths, and assert nothing
    crashes and every fed speaker is eventually visible."""
    audio = FakeAudio()
    n_speakers = 40
    transcribers = [FakeTranscriber([]) for _ in range(n_speakers)]
    deps = _make_deps(tmp_root, transcribers, audio=audio)
    registry = SessionRegistry(deps)
    session = registry.create("session-race", "guild-1")

    errors: list[BaseException] = []
    stop_reading = False

    def feed_worker(i: int) -> None:
        try:
            session.feed(f"speaker-{i}", f"display-{i}", f"frame-{i}".encode(), ts_ms=i)
        except BaseException as exc:  # noqa: BLE001 -- capture any race-induced crash
            errors.append(exc)

    def read_worker() -> None:
        try:
            while not stop_reading:
                session._meta()
                with session._lock:
                    [buf.pcm_path for buf in session._speakers.values() if buf.has_audio()]
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    reader = threading.Thread(target=read_worker)
    reader.start()
    try:
        feeders = [threading.Thread(target=feed_worker, args=(i,)) for i in range(n_speakers)]
        for t in feeders:
            t.start()
        for t in feeders:
            t.join(timeout=10)
    finally:
        stop_reading = True
        reader.join(timeout=10)

    assert errors == []
    assert set(session._speakers.keys()) == {f"speaker-{i}" for i in range(n_speakers)}

    # The session must still be fully usable afterwards (lock released cleanly,
    # no deadlock left behind).
    view = asyncio.run(session.transcript_view())
    assert isinstance(view, list)
    result = asyncio.run(session.stop())
    assert result.transcript == ""
