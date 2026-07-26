"""Adapters bridging ``SessionRegistry``'s injected ``deps`` protocol to the
real ffmpeg/AWS/LLM modules, plus the process-wide ``SessionRegistry`` FastAPI
dependency.

``src/sessions.py`` is deliberately decoupled from ffmpeg/AWS/network so it
unit-tests with fakes. This module is the only place that wires it to the real
world: real ffmpeg subprocess decode/mix, a real AWS Transcribe client
factory, and a real LLM-backed report builder (minutes + PDF).
"""

import tempfile
from datetime import datetime, timezone
from functools import lru_cache

from src.audio.decoder import OpusStreamDecoder, run_ffmpeg
from src.audio.mixer import mix_to_mp3_args
from src.config import get_settings
from src.pipeline.llm_client import LlmClient
from src.pipeline.minutes import summarize_minutes
from src.pipeline.pdf import render_meeting_pdf
from src.pipeline.transcript import assemble_transcript
from src.sessions import SessionRegistry
from src.stt.transcribe import create_transcriber


class AudioAdapter:
    """Factory for per-speaker, stateful Opus decoders.

    Discord voice delivers bare Opus packets (no container/demuxer framing),
    and Opus decode carries state across packets -- so decoding can't be a
    single stateless ``decode(frame)`` call shared across speakers (that was
    the live-integration bug: ffmpeg has no demuxer for standalone Opus
    packets, and failed with exit 234 against real Discord audio). Instead,
    each speaker gets its OWN ``OpusStreamDecoder`` instance (see
    ``make_decoder``), created once in ``_SpeakerBuffer.__init__`` and fed
    that speaker's packets in order for the life of the session.
    """

    def make_decoder(self) -> OpusStreamDecoder:
        return OpusStreamDecoder()


class MixerAdapter:
    """Mixes N raw PCM tracks into one MP3 via ffmpeg.

    ``mix_to_mp3_args`` writes ffmpeg's output to a file path (not stdout), so
    ``run_ffmpeg``'s returned stdout is empty here -- the mixed bytes are read
    back from ``output_path`` after the subprocess exits successfully.
    """

    def mix(self, paths: list[str], output_path: str) -> bytes:
        run_ffmpeg(mix_to_mp3_args(paths, output_path))
        with open(output_path, "rb") as f:
            return f.read()


def _build_report_builder():
    settings = get_settings()
    llm_client = LlmClient(
        settings.llm_base_url, settings.llm_api_key, settings.request_timeout_s
    )

    def report_builder(segments, meta):
        transcript = assemble_transcript(segments)
        minutes = summarize_minutes(transcript, llm_client)
        pdf_bytes = render_meeting_pdf(minutes, transcript, meta)
        return minutes, pdf_bytes

    return report_builder


@lru_cache(maxsize=1)
def get_session_registry() -> SessionRegistry:
    """FastAPI dependency: process-wide ``SessionRegistry`` wired to real
    ffmpeg/AWS/LLM adapters. Tests override via
    ``app.dependency_overrides[get_session_registry] = lambda: fake_registry``."""
    deps = {
        "make_transcriber": lambda: create_transcriber(get_settings().aws_region),
        "audio": AudioAdapter(),
        "mixer": MixerAdapter(),
        "report_builder": _build_report_builder(),
        "tmp_root": tempfile.gettempdir(),
        "now": lambda: datetime.now(timezone.utc),
        "max_meeting_ms": get_settings().max_meeting_ms,
    }
    return SessionRegistry(deps)
