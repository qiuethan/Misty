"""Build ffmpeg args to decode a Discord voice Opus stream into 16 kHz mono s16le PCM."""

import subprocess


def opus_to_pcm16k_args() -> list[str]:
    """Build ffmpeg args reading Opus from stdin, writing 16 kHz mono s16le PCM to stdout.

    INTEGRATION ASSUMPTION (verify live in sub-plan 3):
    Discord/@discordjs/voice's Opus decoder/receiver stream yields bare Opus
    frames (RTP payloads with no container), not an Ogg-framed stream. ffmpeg's
    generic demuxer can't sniff a headerless raw-Opus byte stream reliably, so
    we declare the input codec explicitly with `-c:a libopus -f data` (a raw
    elementary-stream reader) rather than `-f ogg` (which requires Ogg page
    framing/headers the bot does NOT produce unless it wraps each frame itself).
    If the upstream bot instead Ogg-wraps the packets before piping to ffmpeg,
    this must change to `-f ogg -i pipe:0` (drop `-c:a libopus`, since Ogg
    already declares its codec). Confirm which shape the actual byte stream is
    in during live integration testing and adjust accordingly.
    """
    return [
        "-f",
        "data",
        "-c:a",
        "libopus",
        "-i",
        "pipe:0",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "s16le",
        "pipe:1",
    ]


def run_ffmpeg(args: list[str], input_bytes: bytes | None = None) -> bytes:
    """Run ffmpeg with `args`, feeding `input_bytes` to stdin, and return stdout.

    Raises RuntimeError (with the stderr tail) if ffmpeg exits non-zero.
    """
    result = subprocess.run(["ffmpeg", *args], input=input_bytes, capture_output=True)
    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:].decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}): {stderr_tail}")
    return result.stdout
