from src.audio.decoder import opus_to_pcm16k_args
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


def test_opus_to_pcm16k_args_declares_16k_mono_s16le_stdout():
    args = opus_to_pcm16k_args()

    assert "-ar" in args
    assert args[args.index("-ar") + 1] == "16000"
    assert "-ac" in args
    assert args[args.index("-ac") + 1] == "1"
    assert "-f" in args
    assert "s16le" in args
    assert args[-1] == "pipe:1"
