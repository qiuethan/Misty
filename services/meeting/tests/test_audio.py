import math
import struct

import av

from src.audio.decoder import OpusStreamDecoder


def _encode_bare_opus_packet(
    frequency_hz: int = 440, sample_rate: int = 48000, n_samples: int = 960
) -> bytes:
    """Encode one 20 ms, 48 kHz stereo sine-wave frame into a single bare Opus
    packet (no container/demuxer framing) -- exactly the shape Discord voice
    delivers per WS frame. Uses PyAV's own encoder so this is a REAL Opus
    packet, not a hand-rolled fixture."""
    samples: list[int] = []
    for i in range(n_samples):
        value = int(3000 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        samples.append(value)
        samples.append(value)  # stereo: duplicate to both channels
    pcm_bytes = struct.pack(f"<{len(samples)}h", *samples)

    frame = av.AudioFrame(format="s16", layout="stereo", samples=n_samples)
    frame.sample_rate = sample_rate
    frame.planes[0].update(pcm_bytes)

    encoder = av.CodecContext.create("libopus", "w")
    encoder.sample_rate = sample_rate
    encoder.layout = "stereo"
    encoder.format = "s16"
    packets = encoder.encode(frame)
    return b"".join(bytes(p) for p in packets)


def _encode_continuous_stream(n_frames: int, frequency_hz: int = 440) -> list[bytes]:
    """Encode `n_frames` consecutive 20 ms frames of one continuous sine through
    a SINGLE encoder, returning one bare Opus packet per emitted packet -- i.e.
    a realistic per-speaker Discord stream rather than N independent one-shot
    encodes."""
    sample_rate, n_samples = 48000, 960
    encoder = av.CodecContext.create("libopus", "w")
    encoder.sample_rate = sample_rate
    encoder.layout = "stereo"
    encoder.format = "s16"

    packets: list[bytes] = []
    for n in range(n_frames):
        samples: list[int] = []
        for i in range(n_samples):
            t = n * n_samples + i
            value = int(3000 * math.sin(2 * math.pi * frequency_hz * t / sample_rate))
            samples.append(value)
            samples.append(value)
        frame = av.AudioFrame(format="s16", layout="stereo", samples=n_samples)
        frame.sample_rate = sample_rate
        frame.planes[0].update(struct.pack(f"<{len(samples)}h", *samples))
        packets.extend(bytes(p) for p in encoder.encode(frame))
    packets.extend(bytes(p) for p in encoder.encode(None))  # flush
    return packets


def test_decoded_pcm_length_matches_real_audio_duration():
    """The decoded byte count IS the timebase: ``sessions.py`` derives each
    speaker's buffer position from ``len(pcm) // 32`` and maps AWS Transcribe's
    word offsets through it. So decode must emit EXACTLY the audio's worth of
    bytes -- no FFmpeg buffer-alignment padding.

    ``bytes(frame.planes[0])`` returns the whole aligned plane allocation, which
    is larger than ``samples * 2``; splicing that padding into the stream both
    corrupts the audio sent to Transcribe and inflates the buffer timebase,
    which silently suppresses the silence-gap detection in
    ``_SpeakerBuffer._note_anchor``.
    """
    n_frames = 50  # 50 * 20ms == 1000ms of audio
    packets = _encode_continuous_stream(n_frames)

    decoder = OpusStreamDecoder()
    total_bytes = sum(len(decoder.decode(p)) for p in packets)

    # 16 kHz mono s16le == 32 bytes per millisecond.
    decoded_ms = total_bytes / 32
    expected_ms = n_frames * 20

    # Allow only resampler priming (~1ms), NOT per-frame padding (~20%).
    assert abs(decoded_ms - expected_ms) <= 25, (
        f"decoded {decoded_ms:.1f}ms of PCM for {expected_ms}ms of audio "
        f"({decoded_ms / expected_ms * 100 - 100:+.1f}%)"
    )


def test_decode_emits_no_buffer_alignment_padding():
    """Directly pins the per-chunk invariant behind the duration test above:
    every byte returned must be a real sample."""
    decoder = OpusStreamDecoder()
    for packet in _encode_continuous_stream(5):
        pcm = decoder.decode(packet)
        # s16 mono: 2 bytes per sample, so a padded plane shows up as a byte
        # count that isn't a whole number of samples' worth of *real* audio.
        # 20ms at 16kHz is 320 samples / 640 bytes; padding pushes it to 768.
        assert len(pcm) <= 640, f"chunk of {len(pcm)} bytes exceeds one 20ms frame (640)"


def test_opus_stream_decoder_round_trips_a_real_bare_opus_packet_to_16k_mono_pcm():
    """Proves the fix: a real per-speaker OpusStreamDecoder can decode a bare
    (unwrapped) Discord-shaped Opus packet -- the exact input shape that broke
    the old ffmpeg `-f data -c:a libopus` path live (ffmpeg has no demuxer for
    standalone Opus packets, and failed with exit 234 against real Discord
    audio: 'Stream #0:0: Data: none' / 'Output file does not contain any
    stream'). Round-trips a real encoded packet through the decoder and
    asserts it yields non-empty, roughly-20ms-worth-of, 16 kHz mono s16le PCM.
    """
    opus_packet = _encode_bare_opus_packet()
    assert len(opus_packet) > 0  # sanity: we really produced an Opus packet

    decoder = OpusStreamDecoder()
    pcm = decoder.decode(opus_packet)

    assert pcm != b""
    assert len(pcm) % 2 == 0  # s16le: whole 16-bit samples only

    # 20ms @ 16kHz mono s16le == 320 samples == 640 bytes. Resampler priming
    # can withhold a few samples on the FIRST packet, so allow a shortfall --
    # but never an overshoot. A previous `<= 2x` upper bound here is what let
    # 20% buffer-alignment padding go unnoticed; see
    # test_decoded_pcm_length_matches_real_audio_duration.
    expected_bytes = int(960 * 16000 / 48000) * 2
    assert expected_bytes * 0.9 <= len(pcm) <= expected_bytes


def test_opus_stream_decoder_is_stateful_across_multiple_packets_in_order():
    """A single speaker's stream is many sequential packets fed to the SAME
    decoder instance (Opus decode carries state across packets) -- decode a
    short run of real packets in order and assert each yields audio and the
    decoder doesn't blow up or reset itself mid-stream."""
    decoder = OpusStreamDecoder()
    total_pcm = b""
    for _ in range(5):
        packet = _encode_bare_opus_packet()
        pcm = decoder.decode(packet)
        assert pcm != b""
        total_pcm += pcm

    assert len(total_pcm) > 0
    assert len(total_pcm) % 2 == 0


def test_opus_stream_decoder_returns_empty_bytes_for_empty_packet():
    decoder = OpusStreamDecoder()

    assert decoder.decode(b"") == b""


def test_opus_stream_decoder_recovers_from_a_malformed_packet():
    """A single malformed/corrupt Opus packet (e.g. a truncated or garbled
    Discord frame) must not take down the speaker's whole stream: decode is
    best-effort per packet and swallows the libopus decode error, returning
    ``b""``. This exercises the non-empty-but-invalid path past the empty
    guard (the empty-packet test returns before the try/except), so the
    ``except av.error.FFmpegError`` recovery is actually covered -- and the
    decoder keeps working for valid packets fed to it afterward.
    """
    decoder = OpusStreamDecoder()

    assert decoder.decode(b"not a real opus packet") == b""

    # The instance is still usable for real packets after a bad one.
    assert decoder.decode(_encode_bare_opus_packet()) != b""
