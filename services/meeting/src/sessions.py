"""Stateful in-process session registry + meeting lifecycle orchestration.

All collaborators (transcriber factory, audio decoder, mixer, report builder,
tmp dir root, clock) are injected via a ``deps`` dict so this module has zero
direct dependency on ffmpeg/AWS/network -- tests use fakes exclusively.

Design note (deviation from a fully "live" model, flagged for the reviewer):
true incremental transcription would keep a persistent per-speaker Transcribe
stream open and feed it audio as frames arrive. That's an inherently live/
integration concern (a real streaming client, backpressure, concurrent tasks)
that doesn't unit-test cleanly with fakes. Instead, ``feed`` only decodes and
buffers: per-speaker raw PCM is appended to a temp file (for the final audio
mix) AND kept in memory (for transcription input). Transcription itself is
driven by re-running the injected transcriber's ``transcribe()`` over the
speaker's buffered-so-far PCM, both when ``transcript_view()`` is polled
(a "periodic" refinement of the rolling view) and, finally, in ``stop()``.
This is simpler and fully testable with fakes, and is adequate for the
rolling-transcript-at-stop + periodic transcript_view use cases described in
the brief. True incremental/live streaming transcription can be layered in
during the sub-plan 3 live integration phase.
"""

import base64
import os
import shutil

from src.contracts import Segment, StopResponse
from src.pipeline.transcript import assemble_transcript


class SessionAlreadyExistsError(ValueError):
    """Raised by ``SessionRegistry.create`` when the session_id is already active."""


def words_to_segments(speaker: str, words: list[dict], gap_ms: int = 3000) -> list[Segment]:
    """Group a flat, chronological word list into segments for one speaker.

    A new segment starts whenever the gap between a word's start_ms and the
    previous word's start_ms exceeds ``gap_ms``. Same semantics as the MVP.
    """
    segments: list[Segment] = []
    current_words: list[str] = []
    current_start: int | None = None
    last_start: int | None = None

    for word in words:
        start = word["start_ms"]
        if current_words and last_start is not None and (start - last_start) > gap_ms:
            segments.append(Segment(speaker=speaker, start_ms=current_start, text=" ".join(current_words)))
            current_words = []
            current_start = None
        if current_start is None:
            current_start = start
        current_words.append(str(word["text"]))
        last_start = start

    if current_words:
        segments.append(Segment(speaker=speaker, start_ms=current_start, text=" ".join(current_words)))

    return segments


async def _achunks(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


class _SpeakerBuffer:
    def __init__(self, display_name: str, pcm_path: str, transcriber):
        self.display_name = display_name
        self.pcm_path = pcm_path
        self.transcriber = transcriber
        self.pcm_chunks: list[bytes] = []
        # Absolute meeting-relative ts_ms of this speaker's FIRST fed frame. AWS
        # Transcribe's word start_ms values are relative to the start of this
        # speaker's own concatenated PCM buffer (each speaker's audio starts near
        # word start_ms 0), NOT to the meeting's start. We anchor by adding this
        # base offset to every word's start_ms before building segments, so that
        # cross-speaker sorting-by-start_ms in transcript_view()/stop() reflects
        # real chronological (meeting-relative) order instead of each speaker
        # restarting at ~0.
        #
        # Known residual limitation (sub-plan 3 refinement): because each
        # speaker's PCM is a concatenation of only the frames they spoke
        # (inter-utterance silence is never written to their buffer), this base
        # offset anchors only the FIRST word correctly. If a speaker has a long
        # silence mid-meeting and then resumes, later words in that same
        # speaker's buffer will still under-count the elapsed wall-clock gap
        # (Transcribe sees back-to-back audio with no gap). This fixes the
        # gross cross-speaker ordering bug; true per-utterance anchoring
        # (tracking ts_ms per contiguous run of frames, not just the first)
        # is left for the live-integration phase.
        self.base_ts_ms: int | None = None

    def append(self, pcm_bytes: bytes, ts_ms: int | None = None) -> None:
        if self.base_ts_ms is None and ts_ms is not None:
            self.base_ts_ms = ts_ms
        self.pcm_chunks.append(pcm_bytes)
        with open(self.pcm_path, "ab") as f:
            f.write(pcm_bytes)

    def has_audio(self) -> bool:
        return os.path.exists(self.pcm_path) and os.path.getsize(self.pcm_path) > 0

    async def transcribe_buffered(self) -> list[dict]:
        # Snapshot so concurrent feeds don't mutate the list mid-iteration.
        result = await self.transcriber.transcribe(_achunks(list(self.pcm_chunks)), sample_rate=16000)
        words = result.get("words", [])
        base = self.base_ts_ms or 0
        # Offset each Transcribe-relative word start_ms by this speaker's
        # absolute meeting-relative base offset -- see the comment in
        # __init__ for why this is necessary and its known limitation.
        return [{**word, "start_ms": word["start_ms"] + base} for word in words]


class MeetingSession:
    def __init__(self, session_id: str, guild_id: str, deps: dict, on_finalize):
        self.session_id = session_id
        self.guild_id = guild_id
        self._deps = deps
        self._on_finalize = on_finalize
        self._started_at = deps["now"]()
        self._speakers: dict[str, _SpeakerBuffer] = {}
        self._tmp_dir = os.path.join(deps["tmp_root"], session_id)
        os.makedirs(self._tmp_dir, exist_ok=True)
        self._finalized = False

    def feed(self, speaker_id: str, display_name: str, opus_frame_bytes: bytes, ts_ms: int) -> None:
        buf = self._speakers.get(speaker_id)
        if buf is None:
            pcm_path = os.path.join(self._tmp_dir, f"{speaker_id}.pcm")
            transcriber = self._deps["make_transcriber"]()
            buf = _SpeakerBuffer(display_name, pcm_path, transcriber)
            self._speakers[speaker_id] = buf
        else:
            buf.display_name = display_name

        pcm = self._deps["audio"].decode(opus_frame_bytes)
        buf.append(pcm, ts_ms)

    async def transcript_view(self) -> list[Segment]:
        segments: list[Segment] = []
        for buf in self._speakers.values():
            words = await buf.transcribe_buffered()
            segments.extend(words_to_segments(buf.display_name, words))
        segments.sort(key=lambda s: s.start_ms)
        return segments

    def _meta(self) -> dict:
        return {
            "title": f"Meeting {self.session_id}",
            "started_at": str(self._started_at),
            "duration_label": "",
            "participants": [buf.display_name for buf in self._speakers.values()],
        }

    async def stop(self) -> StopResponse:
        try:
            segments: list[Segment] = []
            for buf in self._speakers.values():
                words = await buf.transcribe_buffered()
                segments.extend(words_to_segments(buf.display_name, words))
            segments.sort(key=lambda s: s.start_ms)

            transcript_text = assemble_transcript(segments)
            minutes, pdf_bytes = self._deps["report_builder"](segments, self._meta())
            pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

            audio_b64 = None
            pcm_paths = [buf.pcm_path for buf in self._speakers.values() if buf.has_audio()]
            if pcm_paths:
                output_path = os.path.join(self._tmp_dir, "mix.mp3")
                mp3_bytes = self._deps["mixer"].mix(pcm_paths, output_path)
                audio_b64 = base64.b64encode(mp3_bytes).decode("ascii")

            return StopResponse(
                transcript=transcript_text,
                minutes=minutes,
                pdf_b64=pdf_b64,
                audio_b64=audio_b64,
            )
        finally:
            self._cleanup()

    def discard(self) -> None:
        """Lightweight teardown for abrupt disconnects (e.g. WS drop without a
        preceding ``POST /stop``): delete the session's temp dir and deregister
        it from the registry. Deliberately does NOT transcribe/summarize/build a
        PDF/mix audio -- those are only worth paying for when a consumer
        actually wants the finalized meeting artifacts via ``stop()``.

        Idempotent: safe to call more than once, and safe to call after
        ``stop()`` has already run (both funnel through the same cleanup).
        """
        self._cleanup()

    def _cleanup(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        self._on_finalize(self.session_id)


class SessionRegistry:
    def __init__(self, deps: dict):
        self._deps = deps
        self._sessions: dict[str, MeetingSession] = {}

    def create(self, session_id: str, guild_id: str) -> MeetingSession:
        if session_id in self._sessions:
            raise SessionAlreadyExistsError(session_id)
        session = MeetingSession(session_id, guild_id, self._deps, on_finalize=self._deregister)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> MeetingSession | None:
        return self._sessions.get(session_id)

    def _deregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
