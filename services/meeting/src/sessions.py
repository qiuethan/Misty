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

import asyncio
import base64
import hashlib
import logging
import os
import shutil
import threading

from src.contracts import Segment, StopResponse
from src.pipeline.transcript import assemble_transcript

_logger = logging.getLogger("meeting.audit")


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


def _safe_filename_component(raw: str) -> str:
    """Derive a filesystem-safe, collision-resistant filename component from an
    attacker/caller-controlled speaker_id (decoded straight off the WS binary
    frame, see api/routers/meetings.py -- no charset or path-traversal
    validation happens there). NEVER interpolate the raw speaker_id into a
    filesystem path: values like ``../../etc/evil`` or ``/abs/path`` would
    otherwise let a WS client redirect PCM writes (and the later ffmpeg mix
    read) to an arbitrary path outside the session's tmp dir (CWE-22).

    A hash of the raw id is used (rather than an allowlist substitution) so
    two distinct raw ids collide onto the same sanitized filename only with
    negligible probability (a 128-bit truncation of a cryptographic hash --
    not a mathematical impossibility, but not a practical concern either).
    The raw speaker_id itself is preserved untouched as the dict key / for
    display_name mapping -- only the on-disk path uses this sanitized value.
    """
    return hashlib.sha256(raw.encode("utf-8", errors="surrogateescape")).hexdigest()[:32]


async def _achunks(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


class _SpeakerBuffer:
    def __init__(self, display_name: str, pcm_path: str, transcriber, decoder):
        self.display_name = display_name
        self.pcm_path = pcm_path
        self.transcriber = transcriber
        # Opus decode is STATEFUL per stream (packet-loss concealment,
        # internal decoder history) -- this speaker's own decoder instance
        # must be fed only this speaker's packets, in order, for the life of
        # the session. See src/audio/decoder.py's OpusStreamDecoder docstring.
        self.decoder = decoder
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

    async def transcribe_buffered(self, pcm_chunks: list[bytes]) -> list[dict]:
        # ``pcm_chunks`` must already be an immutable snapshot taken by the
        # caller (MeetingSession) under ``self._lock`` -- this method itself
        # does no locking so it's safe to ``await`` here without holding
        # anything that feed() (running on a worker thread) needs.
        result = await self.transcriber.transcribe(_achunks(pcm_chunks), sample_rate=16000)
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
        # Guards all reads/mutations of self._speakers (dict shape) and of any
        # individual buffer's pcm_chunks list. feed() runs synchronously on a
        # worker thread (via asyncio.to_thread from the WS ingest loop) while
        # transcript_view()/stop()/_meta() run on the event-loop thread -- a
        # plain dict/list is not safe under that cross-thread access pattern
        # (e.g. a comprehension over self._speakers.values() can raise
        # "dictionary changed size during iteration" if feed() inserts a new
        # speaker mid-comprehension). Non-reentrant by design: lock scopes
        # below are kept small and never nested, and never held across an
        # ``await``.
        self._lock = threading.Lock()
        self._tmp_dir = os.path.join(deps["tmp_root"], session_id)
        os.makedirs(self._tmp_dir, exist_ok=True)
        self._finalized = False
        self._cap_hit_logged = False

    def feed(self, speaker_id: str, display_name: str, opus_frame_bytes: bytes, ts_ms: int) -> None:
        # Fix #4 (cap only -- NOT a fix for the separate re-billing cost issue
        # below): bound unbounded PCM growth by refusing to buffer audio past
        # max_meeting_ms. This does NOT address transcript_view()/stop() still
        # re-transcribing the WHOLE buffer on every poll (re-billing AWS on
        # every call) -- that is a distinct cost problem whose proper fix is
        # the incremental persistent-per-speaker-Transcribe-stream redesign
        # scoped to sub-plan 3, not this cap.
        max_meeting_ms = self._deps.get("max_meeting_ms")
        if max_meeting_ms is not None:
            elapsed_ms = (self._deps["now"]() - self._started_at).total_seconds() * 1000
            if elapsed_ms > max_meeting_ms:
                if not self._cap_hit_logged:
                    self._cap_hit_logged = True
                    _logger.warning(
                        "session %s exceeded max_meeting_ms=%s (elapsed=%.0fms); "
                        "dropping further audio frames",
                        self.session_id,
                        max_meeting_ms,
                        elapsed_ms,
                    )
                return

        # Get-or-create this speaker's buffer (and its OWN stateful Opus
        # decoder) under the lock -- creation touches shared state
        # (self._speakers).
        with self._lock:
            buf = self._speakers.get(speaker_id)
            if buf is None:
                pcm_path = os.path.join(self._tmp_dir, f"{_safe_filename_component(speaker_id)}.pcm")
                transcriber = self._deps["make_transcriber"]()
                decoder = self._deps["audio"].make_decoder()
                buf = _SpeakerBuffer(display_name, pcm_path, transcriber, decoder)
                self._speakers[speaker_id] = buf
            else:
                buf.display_name = display_name

        # Opus decode is CPU work with no shared-state touch (each speaker's
        # decoder is only ever driven by this speaker's own feed() calls) --
        # do it OUTSIDE the lock so it doesn't block readers any longer than
        # necessary.
        pcm = buf.decoder.decode(opus_frame_bytes)

        with self._lock:
            buf.append(pcm, ts_ms)

    async def transcript_view(self) -> list[Segment]:
        segments: list[Segment] = []
        # Snapshot BOTH the speaker list and each buffer's accumulated PCM
        # under the lock, then release it before doing any async transcribe
        # work. feed() runs synchronously on a worker thread (via
        # asyncio.to_thread from the live WS ingest loop) and can insert a
        # brand-new speaker into self._speakers, or append to an existing
        # buffer's pcm_chunks, at any time -- including while this coroutine
        # is suspended at an `await`. Snapshotting under a short, non-async
        # lock section avoids both "dictionary changed size during iteration"
        # and mutating the list mid-transcribe. A speaker who first appears
        # (or speaks more) mid-poll simply shows up fully on the next poll (or
        # at stop()) instead -- an acceptable, self-correcting gap.
        with self._lock:
            snapshot = [(buf, list(buf.pcm_chunks)) for buf in self._speakers.values()]
        for buf, pcm_chunks in snapshot:
            words = await buf.transcribe_buffered(pcm_chunks)
            segments.extend(words_to_segments(buf.display_name, words))
        segments.sort(key=lambda s: s.start_ms)
        return segments

    def _meta(self) -> dict:
        elapsed_s = (self._deps["now"]() - self._started_at).total_seconds()
        minutes = max(0, int(elapsed_s // 60))
        with self._lock:
            participants = [buf.display_name for buf in self._speakers.values()]
        return {
            "title": f"Meeting {self.session_id}",
            "started_at": str(self._started_at),
            "duration_label": f"{minutes}m",
            "participants": participants,
        }

    async def stop(self) -> StopResponse:
        try:
            segments: list[Segment] = []
            # Same lock-scoped snapshot rationale as transcript_view() above:
            # a concurrent feed() must not mutate self._speakers or a
            # buffer's pcm_chunks while we're suspended at the await below.
            with self._lock:
                snapshot = [(buf, list(buf.pcm_chunks)) for buf in self._speakers.values()]
            for buf, pcm_chunks in snapshot:
                words = await buf.transcribe_buffered(pcm_chunks)
                segments.extend(words_to_segments(buf.display_name, words))
            segments.sort(key=lambda s: s.start_ms)

            transcript_text = assemble_transcript(segments)
            # Fix #2: report_builder is sync and does a blocking LLM HTTP call
            # (up to request_timeout_s, default 60s) plus PDF rendering. Offload
            # to a thread so it doesn't stall the event loop for other meetings.
            # The sync internals (llm_client/minutes/pdf) are intentionally left
            # as-is -- thread-offloading at this async boundary is the chosen
            # fix, not an async rewrite of those modules.
            minutes, pdf_bytes = await asyncio.to_thread(
                self._deps["report_builder"], segments, self._meta()
            )
            pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

            audio_b64 = None
            with self._lock:
                pcm_paths = [buf.pcm_path for buf in self._speakers.values() if buf.has_audio()]
            if pcm_paths:
                output_path = os.path.join(self._tmp_dir, "mix.mp3")
                # Fix #2: mixer.mix() shells out to ffmpeg synchronously (subprocess.run).
                # Offload to a thread for the same reason as report_builder above.
                mp3_bytes = await asyncio.to_thread(self._deps["mixer"].mix, pcm_paths, output_path)
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
