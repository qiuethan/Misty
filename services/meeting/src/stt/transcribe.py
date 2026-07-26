"""AWS Transcribe streaming wrapper over the async ``amazon-transcribe`` client.

The real client (``amazon_transcribe.client.TranscribeStreamingClient``) is only
imported lazily, and only when a client isn't injected — this keeps tests free
of any AWS SDK/network/credential dependency.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterable

LANGUAGE_CODE = "en-US"
MEDIA_ENCODING = "pcm"
PRONUNCIATION_ITEM_TYPE = "pronunciation"


class _ResultAccumulator:
    """Consumes an amazon-transcribe output_stream, keeping only final results."""

    def __init__(self, output_stream):
        self._output_stream = output_stream
        self.transcript_parts: list[str] = []
        self.words: list[dict] = []

    async def consume(self) -> None:
        async for event in self._output_stream:
            transcript = getattr(event, "transcript", None)
            if transcript is None:
                continue
            for result in transcript.results or []:
                if result.is_partial:
                    continue
                self._accumulate_result(result)

    def _accumulate_result(self, result) -> None:
        if not result.alternatives:
            return
        alternative = result.alternatives[0]
        if alternative.transcript:
            self.transcript_parts.append(alternative.transcript)
        for item in alternative.items or []:
            if item.item_type != PRONUNCIATION_ITEM_TYPE:
                continue
            self.words.append(
                {
                    "text": item.content,
                    "start_ms": round((item.start_time or 0.0) * 1000),
                }
            )


class _Transcriber:
    def __init__(self, region: str, client=None):
        self._region = region
        self._client = client

    def _resolve_client(self):
        if self._client is None:
            from amazon_transcribe.client import TranscribeStreamingClient

            self._client = TranscribeStreamingClient(region=self._region)
        return self._client

    async def transcribe(self, pcm_chunks: AsyncIterable[bytes], sample_rate: int = 16000) -> dict:
        client = self._resolve_client()
        stream = await client.start_stream_transcription(
            language_code=LANGUAGE_CODE,
            media_sample_rate_hz=sample_rate,
            media_encoding=MEDIA_ENCODING,
        )

        accumulator = _ResultAccumulator(stream.output_stream)

        async def _send_audio() -> None:
            async for chunk in pcm_chunks:
                await stream.input_stream.send_audio_event(audio_chunk=chunk)
            await stream.input_stream.end_stream()

        consume_task = asyncio.ensure_future(accumulator.consume())
        try:
            await _send_audio()
            await consume_task
        finally:
            if not consume_task.done():
                consume_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await consume_task

        return {
            "text": " ".join(accumulator.transcript_parts),
            "words": accumulator.words,
        }


def create_transcriber(region: str, client=None):
    """Build a transcriber. ``client`` is injectable (tests use a fake, no network)."""
    return _Transcriber(region, client=client)
