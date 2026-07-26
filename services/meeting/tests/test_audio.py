import math
import struct

import av

from src.audio.decoder import OpusStreamDecoder
from src.audio.mixer import mix_to_mp3_args


def test_mix_to_mp3_args_declares_each_input_as_raw_pcm_and_mixes():
    args = mix_to_mp3_args(["/a.pcm", "/b.pcm"], "/o.mp3")

    assert "amix=inputs=2" in " ".join(args)
    # Each input must be declared as raw 16kHz mono s16le before its -i.
    assert args.count("-f") >= 2
    assert args.count("s16le") >= 2
    assert args.count("-ar") >= 2
    assert args.count("16000") >= 2
    assert args.count("-ac") >= 2
    assert args.count("-i") == 2
    assert "/a.pcm" in args
    assert "/b.pcm" in args
    assert "libmp3lame" in args
    assert args[-1] == "/o.mp3"


def test_mix_to_mp3_args_repeats_input_flags_per_input():
    args = mix_to_mp3_args(["/a.pcm", "/b.pcm", "/c.pcm"], "/o.mp3")

    assert "amix=inputs=3" in " ".join(args)
    assert args.count("-i") == 3


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

    # 20ms @ 16kHz mono s16le == 320 samples == 640 bytes. Resampler filter
    # delay/padding can shift this a bit, so assert "roughly" rather than
    # exact equality.
    expected_bytes = int(960 * 16000 / 48000) * 2
    assert expected_bytes * 0.5 <= len(pcm) <= expected_bytes * 2


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
