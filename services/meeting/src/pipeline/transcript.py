def format_timestamp(ms: int) -> str:
    total = max(0, ms // 1000)
    return f"{total // 60:02d}:{total % 60:02d}"


def _get(seg, key):
    return seg[key] if isinstance(seg, dict) else getattr(seg, key)


def assemble_transcript(segments) -> str:
    indexed = [(i, s) for i, s in enumerate(segments or []) if str(_get(s, "text")).strip()]
    indexed.sort(key=lambda pair: (_get(pair[1], "start_ms"), pair[0]))
    return "\n".join(
        f"[{format_timestamp(_get(s, 'start_ms'))}] {_get(s, 'speaker')}: {str(_get(s, 'text')).strip()}"
        for _, s in indexed
    )
