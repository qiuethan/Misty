"""Build ffmpeg args to mix N raw 16 kHz mono s16le PCM inputs into one MP3."""


def mix_to_mp3_args(input_paths: list[str], output_path: str) -> list[str]:
    """Build ffmpeg args mixing `input_paths` (raw 16kHz mono s16le PCM) into `output_path` (MP3).

    Each input is declared as raw 16 kHz mono s16le PCM (`-f s16le -ar 16000 -ac 1`)
    immediately before its own `-i`, since ffmpeg applies input flags per-input in
    the order they're given on the command line.
    """
    args: list[str] = ["-y"]
    for path in input_paths:
        args += ["-f", "s16le", "-ar", "16000", "-ac", "1", "-i", path]

    args += [
        "-filter_complex",
        f"amix=inputs={len(input_paths)}",
        "-c:a",
        "libmp3lame",
        output_path,
    ]
    return args
