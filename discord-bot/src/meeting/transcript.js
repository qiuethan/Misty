export function formatTimestamp(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function assembleTranscript(segments) {
  return (segments ?? [])
    .filter((seg) => (seg.text ?? '').trim().length > 0)
    .map((seg, i) => ({ ...seg, i }))
    .sort((a, b) => a.startMs - b.startMs || a.i - b.i)
    .map((seg) => `[${formatTimestamp(seg.startMs)}] ${seg.speaker}: ${seg.text.trim()}`)
    .join('\n');
}
