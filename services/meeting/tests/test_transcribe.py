"""Tests for the AWS Transcribe streaming wrapper, using a fake client (no network)."""

import asyncio

import pytest
from amazon_transcribe.model import Alternative, Item, Result, Transcript, TranscriptEvent

from src.stt.transcribe import create_transcriber


class _FakeOutputStream:
    """Mimics amazon_transcribe's TranscriptResultStream: an async-iterable of events."""

    def __init__(self, events):
        self._events = events

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self._events:
            yield event


class _FakeInputStream:
    """Mimics amazon_transcribe's AudioStream (input_stream)."""

    def __init__(self):
        self.sent_chunks = []
        self.ended = False

    async def send_audio_event(self, audio_chunk):
        self.sent_chunks.append(audio_chunk)

    async def end_stream(self):
        self.ended = True


class _FakeStream:
    """Mimics StartStreamTranscriptionEventStream (.input_stream / .output_stream)."""

    def __init__(self, events):
        self.input_stream = _FakeInputStream()
        self.output_stream = _FakeOutputStream(events)


class _FakeClient:
    """Mimics TranscribeStreamingClient.start_stream_transcription — no network."""

    def __init__(self, events):
        self._events = events
        self.calls = []
        self.stream = None

    async def start_stream_transcription(self, **kwargs):
        self.calls.append(kwargs)
        self.stream = _FakeStream(self._events)
        return self.stream


def _partial_event() -> TranscriptEvent:
    alternative = Alternative(
        transcript="hel",
        items=[Item(start_time=0.1, end_time=0.3, item_type="pronunciation", content="hel")],
        entities=None,
    )
    result = Result(
        result_id="r1", start_time=0.1, end_time=0.3, is_partial=True, alternatives=[alternative]
    )
    return TranscriptEvent(transcript=Transcript(results=[result]))


def _final_event() -> TranscriptEvent:
    alternative = Alternative(
        transcript="hello world",
        items=[
            Item(start_time=0.1, end_time=0.4, item_type="pronunciation", content="hello"),
            Item(start_time=0.4, end_time=0.42, item_type="punctuation", content=","),
            Item(start_time=0.512, end_time=0.9, item_type="pronunciation", content="world"),
        ],
        entities=None,
    )
    result = Result(
        result_id="r1", start_time=0.1, end_time=0.9, is_partial=False, alternatives=[alternative]
    )
    return TranscriptEvent(transcript=Transcript(results=[result]))


async def _fake_pcm_chunks():
    yield b"\x00\x01"
    yield b"\x02\x03"


def test_transcribe_accumulates_only_final_results_no_network():
    client = _FakeClient([_partial_event(), _final_event()])
    transcriber = create_transcriber(region="us-east-1", client=client)

    result = asyncio.run(transcriber.transcribe(_fake_pcm_chunks(), sample_rate=16000))

    assert result["text"] == "hello world"
    # Only pronunciation items from the FINAL result; partial ("hel") is skipped.
    assert result["words"] == [
        {"text": "hello", "start_ms": 100},
        {"text": "world", "start_ms": 512},
    ]


def test_transcribe_feeds_audio_and_ends_stream_and_uses_pcm_config():
    client = _FakeClient([_final_event()])
    transcriber = create_transcriber(region="us-east-1", client=client)

    asyncio.run(transcriber.transcribe(_fake_pcm_chunks(), sample_rate=16000))

    assert client.calls == [
        {
            "language_code": "en-US",
            "media_sample_rate_hz": 16000,
            "media_encoding": "pcm",
        }
    ]
    assert client.stream.input_stream.sent_chunks == [b"\x00\x01", b"\x02\x03"]
    assert client.stream.input_stream.ended is True


class _HangingOutputStream:
    """Never yields an event on its own — mimics a stream that would hang forever
    once the AWS side stops receiving events (e.g. because sending failed and
    end_stream() was never reached)."""

    def __init__(self):
        self.was_cancelled = False

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        yield  # pragma: no cover -- unreachable, only makes this an async generator


class _FailingInputStream:
    async def send_audio_event(self, audio_chunk):
        # Yield control first so the concurrently-scheduled consumer task gets a
        # chance to actually start running (and reach its hang point) before we
        # fail — mirrors a real network call, which always yields.
        await asyncio.sleep(0)
        raise RuntimeError("network blip")

    async def end_stream(self):
        pass  # pragma: no cover -- never reached; send fails first


class _FailingStream:
    def __init__(self):
        self.input_stream = _FailingInputStream()
        self.output_stream = _HangingOutputStream()


class _FailingClient:
    def __init__(self):
        self.stream = _FailingStream()

    async def start_stream_transcription(self, **kwargs):
        return self.stream


def test_send_audio_failure_cancels_dangling_consumer_task():
    client = _FailingClient()
    transcriber = create_transcriber(region="us-east-1", client=client)

    with pytest.raises(RuntimeError, match="network blip"):
        asyncio.run(transcriber.transcribe(_fake_pcm_chunks(), sample_rate=16000))

    # The consumer must have been cancelled rather than left dangling forever.
    assert client.stream.output_stream.was_cancelled is True
