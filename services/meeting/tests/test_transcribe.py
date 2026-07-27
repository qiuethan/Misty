"""Tests for the AWS Transcribe streaming wrapper, using a fake client (no network)."""

import asyncio

from amazon_transcribe.model import Alternative, Item, Result, Transcript, TranscriptEvent

from src.stt.transcribe import create_transcription_stream


class _FakeInputStream:
    """Mimics amazon_transcribe's AudioStream (input_stream)."""

    def __init__(self):
        self.sent_chunks = []
        self.ended = False

    async def send_audio_event(self, audio_chunk):
        self.sent_chunks.append(audio_chunk)

    async def end_stream(self):
        self.ended = True


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


# --- persistent per-speaker streaming ---------------------------------------


class _LiveOutputStream:
    """An output stream fed events on demand, so a test can control WHEN results
    become visible -- mimicking AWS emitting finals as the speaker talks rather
    than all at once at the end."""

    def __init__(self):
        self._queue = asyncio.Queue()
        self.closed = False

    def push(self, event):
        self._queue.put_nowait(event)

    def finish(self):
        self._queue.put_nowait(None)

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        while True:
            event = await self._queue.get()
            if event is None:
                self.closed = True
                return
            yield event


class _LiveStream:
    def __init__(self):
        self.output_stream = _LiveOutputStream()
        self.input_stream = _FakeInputStream()
        # Faithful to the real service: ending the input stream makes AWS flush
        # its remaining results and CLOSE the output stream. Without this the
        # fake would let a consumer wait on it forever, which the real one never
        # does.
        _end = self.input_stream.end_stream

        async def end_stream():
            await _end()
            self.output_stream.finish()

        self.input_stream.end_stream = end_stream


class _LiveClient:
    def __init__(self):
        self.streams = []
        self.calls = []

    async def start_stream_transcription(self, **kwargs):
        self.calls.append(kwargs)
        stream = _LiveStream()
        self.streams.append(stream)
        return stream


def test_streaming_sends_audio_once_and_exposes_words_as_they_finalize():
    """The persistent stream: audio pushed in with send() reaches AWS exactly
    once, and finalized words become readable via words() WITHOUT closing or
    re-sending anything."""

    async def scenario():
        client = _LiveClient()
        stream = create_transcription_stream(region="us-east-1", client=client)
        stream.start()

        stream.send(b"\x00" * 640)
        stream.send(b"\x01" * 640)
        await stream.drain()

        assert stream.words() == []  # nothing finalized yet

        client.streams[0].output_stream.push(_final_event())
        await stream.drain()

        # Readable mid-flight, with the stream still open.
        assert stream.words() == [
            {"text": "hello", "start_ms": 100},
            {"text": "world", "start_ms": 512},
        ]
        assert client.streams[0].input_stream.ended is False

        words = await stream.aclose()
        assert words == [
            {"text": "hello", "start_ms": 100},
            {"text": "world", "start_ms": 512},
        ]
        # Exactly one AWS stream, each chunk sent exactly once.
        assert len(client.streams) == 1
        assert client.streams[0].input_stream.sent_chunks == [b"\x00" * 640, b"\x01" * 640]
        assert client.streams[0].input_stream.ended is True

    asyncio.run(scenario())


def test_streaming_reopens_after_the_aws_stream_ends_and_offsets_word_times():
    """AWS ends a streaming session on its own (idle timeout, or the 4h cap). If
    the speaker talks again afterwards we must transparently open a NEW stream --
    and offset its word times by the audio already sent, because each stream
    reports times relative to its own start."""

    async def scenario():
        client = _LiveClient()
        stream = create_transcription_stream(region="us-east-1", client=client)
        stream.start()

        # 1000ms of audio through the first stream, which then ends by itself.
        stream.send(b"\x00" * (32 * 1000))
        await stream.drain()
        client.streams[0].output_stream.push(_final_event())
        client.streams[0].output_stream.finish()
        await stream.drain()

        # The speaker resumes: a second stream opens transparently.
        stream.send(b"\x02" * 640)
        await stream.drain()
        client.streams[1].output_stream.push(_final_event())
        words = await stream.aclose()

        assert len(client.streams) == 2, "a new stream must be opened after the first ends"
        # Second stream's words repeat start_ms 100/512, but land 1000ms later
        # because 1000ms of audio preceded them.
        assert words == [
            {"text": "hello", "start_ms": 100},
            {"text": "world", "start_ms": 512},
            {"text": "hello", "start_ms": 1100},
            {"text": "world", "start_ms": 1512},
        ]

    asyncio.run(scenario())


def test_streaming_abort_is_sync_and_stops_the_stream():
    """discard() (abrupt WS drop) is synchronous and must still tear the AWS
    stream down rather than leaking it until its idle timeout."""

    async def scenario():
        client = _LiveClient()
        stream = create_transcription_stream(region="us-east-1", client=client)
        stream.start()
        stream.send(b"\x00" * 640)
        await stream.drain()

        stream.abort()  # sync, no await

        # Cancellation still has to propagate through the pump's nested waits,
        # so give the loop turns to settle rather than assuming a fixed number.
        for _ in range(100):
            if not stream.is_running():
                break
            await asyncio.sleep(0)

        assert stream.is_running() is False
        # And it must stay torn down -- no reopen behind our back.
        assert stream.words() == []

    asyncio.run(scenario())


def test_streaming_survives_a_failing_stream_and_keeps_earlier_words():
    """A mid-meeting AWS/network failure must not crash the meeting: words
    already finalized are kept and the speaker's later audio is simply dropped
    rather than propagating an exception into the WS ingest loop."""

    class _ExplodingClient:
        def __init__(self):
            self.calls = 0

        async def start_stream_transcription(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                stream = _LiveStream()
                self.first = stream
                return stream
            raise RuntimeError("AWS is unhappy")

    async def scenario():
        client = _ExplodingClient()
        stream = create_transcription_stream(region="us-east-1", client=client)
        stream.start()
        stream.send(b"\x00" * 640)
        await stream.drain()
        client.first.output_stream.push(_final_event())
        await stream.drain()
        # First stream ends; reopening will raise.
        client.first.output_stream.finish()
        await stream.drain()
        stream.send(b"\x01" * 640)
        await stream.drain()

        words = await stream.aclose()
        assert words == [
            {"text": "hello", "start_ms": 100},
            {"text": "world", "start_ms": 512},
        ]

    asyncio.run(scenario())


def test_streaming_ignores_partial_results():
    """AWS emits partial hypotheses that get revised. Only finalized results may
    reach the transcript, or words would appear and then change under the
    reader."""

    async def scenario():
        client = _LiveClient()
        stream = create_transcription_stream(region="us-east-1", client=client)
        stream.start()
        stream.send(b"\x00" * 640)
        await stream.drain()

        client.streams[0].output_stream.push(_partial_event())
        await stream.drain()
        assert stream.words() == [], "a partial result must not be surfaced"

        client.streams[0].output_stream.push(_final_event())
        words = await stream.aclose()
        assert words == [
            {"text": "hello", "start_ms": 100},
            {"text": "world", "start_ms": 512},
        ]

    asyncio.run(scenario())
