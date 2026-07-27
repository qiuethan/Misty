"""AWS Transcribe streaming wrapper over the async ``amazon-transcribe`` client.

One ``_StreamingTranscription`` per speaker, held open for the whole meeting:
audio is pushed in as it arrives and never replayed, so each second of speech is
billed exactly once and reading the rolling transcript is free.

The real client (``amazon_transcribe.client.TranscribeStreamingClient``) is only
imported lazily, and only when a client isn't injected — this keeps tests free
of any AWS SDK/network/credential dependency.
"""

import asyncio
import contextlib
import logging

LANGUAGE_CODE = "en-US"
MEDIA_ENCODING = "pcm"
PRONUNCIATION_ITEM_TYPE = "pronunciation"

# 16 kHz mono s16le -> 32 bytes per millisecond.
_BYTES_PER_MS = 32

# How long aclose() waits for AWS to flush its final results after end_stream().
FINAL_FLUSH_TIMEOUT_S = 15

_logger = logging.getLogger("meeting.audit")


def _words_from_result(result, offset_ms: int = 0) -> list[dict]:
    """Pronunciation items of a FINAL result, as {text, start_ms} shifted by
    ``offset_ms`` (the audio already sent through earlier AWS sessions)."""
    if not result.alternatives:
        return []
    return [
        {"text": item.content, "start_ms": round((item.start_time or 0.0) * 1000) + offset_ms}
        for item in (result.alternatives[0].items or [])
        if item.item_type == PRONUNCIATION_ITEM_TYPE
    ]


class _StreamingTranscription:
    """One speaker's PERSISTENT Transcribe session.

    Audio is pushed in with ``send()`` as it arrives and is never replayed, so
    each second of speech is billed exactly once and reading the rolling
    transcript costs nothing. (This replaced a one-shot transcriber that re-ran
    over a speaker's whole accumulated buffer on every poll, making AWS cost
    grow with the SQUARE of meeting length and each poll progressively slower.)

    Threading: ``send()`` is called from the WS ingest worker thread, while the
    pump runs on the event loop. Handoff goes through ``call_soon_threadsafe``,
    so ``send()`` never blocks the ingest path and never touches asyncio state
    from the wrong thread.

    Restarts: AWS ends a streaming session on its own (idle timeout, or the 4h
    per-stream cap). Each session reports word times relative to ITS OWN start,
    so ``_sent_ms_at_stream_start`` shifts each new session's words back onto
    the speaker's single continuous buffer timeline -- which is the timebase
    ``sessions.py``'s anchors expect.
    """

    def __init__(self, region: str, client=None, sample_rate: int = 16000):
        self._region = region
        self._client = client
        self._sample_rate = sample_rate
        self._queue: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._words: list[dict] = []
        self._closing = False
        # Bytes handed to AWS across ALL sessions so far, and the count at the
        # point the CURRENT session began -- the offset applied to its words.
        self._sent_bytes = 0
        self._sent_bytes_at_stream_start = 0
        self._delivered_bytes = 0

    def _resolve_client(self):
        if self._client is None:
            from amazon_transcribe.client import TranscribeStreamingClient

            self._client = TranscribeStreamingClient(region=self._region)
        return self._client

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Arm the stream. SYNCHRONOUS and callable from any thread, because
        speakers are first seen inside ``feed()``, which runs on the WS ingest
        worker thread -- there is no running loop there to await on. ``loop``
        must therefore be passed in from the event-loop side (the session
        captures it at construction); it defaults to the running loop when
        called from the loop itself, as tests do.
        """
        self._loop = loop or asyncio.get_running_loop()
        self._queue = asyncio.Queue()

        def _spawn() -> None:
            self._task = asyncio.ensure_future(self._pump())

        self._loop.call_soon_threadsafe(_spawn)

    def send(self, pcm: bytes) -> None:
        """Queue audio for AWS. Safe to call from a worker thread; never blocks.

        Dropped silently once closing/closed -- a late frame has nowhere to go,
        and raising here would propagate into the WS ingest loop.
        """
        if self._closing or self._loop is None or self._queue is None:
            return
        self._sent_bytes += len(pcm)
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, pcm)
        except RuntimeError:
            pass  # loop already closed; nothing to do

    def words(self) -> list[dict]:
        """Finalized words so far, on the speaker's buffer timeline. A read --
        no AWS call, no audio replayed."""
        return list(self._words)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _await_task(self) -> None:
        """Wait for the pump, tolerating the window before _spawn() has run."""
        for _ in range(100):
            if self._task is not None:
                break
            await asyncio.sleep(0)

    async def drain(self) -> None:
        """Let the pump catch up: every byte queued has reached AWS and every
        event AWS has emitted has been consumed. Bounded so a wedged or failed
        pump can never hang the caller.

        Used by tests to make the async handoff deterministic; production code
        just calls send() and reads words().
        """
        if self._queue is None:
            return
        for _ in range(1000):
            if (
                self._queue.empty()
                and self._delivered_bytes == self._sent_bytes
            ) or (self._task is not None and self._task.done()):
                break
            await asyncio.sleep(0)
        # A few more turns so the output consumer can process whatever arrived.
        for _ in range(50):
            await asyncio.sleep(0)

    async def aclose(self) -> list[dict]:
        """Flush, end the AWS stream, wait for its final results, return all
        words. Closing is what turns AWS's trailing partial results into finals,
        so this can yield more than the last ``words()`` did."""
        self._closing = True
        await self._await_task()
        if self._queue is not None:
            self._queue.put_nowait(None)  # sentinel: no more audio
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # abort() raced this close; keep whatever was finalized
            except Exception as exc:  # noqa: BLE001 -- finalize must not raise
                _logger.warning("transcription stream ended with an error: %s", exc)
        return list(self._words)

    def abort(self) -> None:
        """Synchronous teardown for an abrupt disconnect (``discard()``). Cancels
        the pump so the AWS stream is released instead of lingering until its
        idle timeout. Fire-and-forget: no results are collected."""
        self._closing = True
        if self._task is not None and not self._task.done():
            self._task.cancel()

    async def _pump(self) -> None:
        """Own the AWS session(s) for this speaker's whole lifetime."""
        pending: list[bytes] = []
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break
            pending.append(chunk)
            # Only open a session once there is actually audio -- a speaker who
            # never talks should never cost anything.
            try:
                if await self._run_session(pending):
                    break  # sentinel consumed inside the session: we're done
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- a dead stream must not kill the meeting
                _logger.warning("transcription session failed, dropping audio: %s", exc)
                pending.clear()
                # Keep draining so send() never backs up, but stop transcribing:
                # words already finalized are preserved.
                await self._drain_remaining()
                return

    async def _drain_remaining(self) -> None:
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                return

    async def _run_session(self, pending: list[bytes]) -> bool:
        """Run ONE AWS streaming session until it ends, feeding it queued audio.

        Returns True if the close sentinel was consumed (nothing more is
        coming), False if AWS ended the session on its own -- in which case the
        caller reopens when the speaker next talks.
        """
        client = self._resolve_client()
        # Offset = audio already DELIVERED to earlier AWS sessions. Not
        # ``_sent_bytes``, which also counts audio still sitting in the queue
        # and about to go through THIS session at its own relative time zero.
        self._sent_bytes_at_stream_start = self._delivered_bytes
        stream = await client.start_stream_transcription(
            language_code=LANGUAGE_CODE,
            media_sample_rate_hz=self._sample_rate,
            media_encoding=MEDIA_ENCODING,
        )
        offset_ms = self._sent_bytes_at_stream_start // _BYTES_PER_MS

        finished = asyncio.Event()

        async def consume() -> None:
            try:
                async for event in stream.output_stream:
                    transcript = getattr(event, "transcript", None)
                    if transcript is None:
                        continue
                    for result in transcript.results or []:
                        if result.is_partial:
                            continue
                        self._words.extend(_words_from_result(result, offset_ms))
            finally:
                finished.set()

        consume_task = asyncio.ensure_future(consume())
        ended = False
        try:
            for chunk in pending:
                await stream.input_stream.send_audio_event(audio_chunk=chunk)
                self._delivered_bytes += len(chunk)
            pending.clear()

            while True:
                get_next = asyncio.ensure_future(self._queue.get())
                done, _ = await asyncio.wait(
                    {get_next, consume_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if get_next in done:
                    chunk = get_next.result()
                    if chunk is None:  # sentinel from aclose()
                        await stream.input_stream.end_stream()
                        ended = True
                        # AWS flushes its last results and closes the output
                        # stream in response to end_stream(). Bound the wait
                        # anyway: a service that never closes would otherwise
                        # hang stop() -- and with it the whole meeting finalize
                        # -- indefinitely. Words already finalized are kept.
                        try:
                            await asyncio.wait_for(consume_task, FINAL_FLUSH_TIMEOUT_S)
                        except asyncio.TimeoutError:
                            _logger.warning(
                                "timed out waiting %ss for final Transcribe results",
                                FINAL_FLUSH_TIMEOUT_S,
                            )
                        return True
                    await stream.input_stream.send_audio_event(audio_chunk=chunk)
                    self._delivered_bytes += len(chunk)
                    continue
                # The AWS side ended this session on its own. Anything already
                # pulled off the queue must be replayed into the next one.
                get_next.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    leftover = await get_next
                    if leftover is not None:
                        pending.append(leftover)
                await consume_task
                return False
        finally:
            if not consume_task.done():
                consume_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await consume_task
            if not ended:
                with contextlib.suppress(Exception):
                    await stream.input_stream.end_stream()


def create_transcription_stream(region: str, client=None, sample_rate: int = 16000):
    """Build one speaker's persistent transcription stream. ``client`` is
    injectable (tests use a fake, no network)."""
    return _StreamingTranscription(region, client=client, sample_rate=sample_rate)
