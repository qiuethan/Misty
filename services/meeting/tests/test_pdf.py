from src.pipeline.pdf import render_meeting_pdf
from src.contracts import Minutes

META = {"title": "T", "started_at": "2026-07-25 18:00", "duration_label": "12m", "participants": ["a", "b"]}


def test_returns_pdf_bytes():
    out = render_meeting_pdf(Minutes(summary="s", decisions=["d"], action_items=["a"]), "[00:00] a: hi", META)
    assert isinstance(out, (bytes, bytearray)) and out[:4] == b"%PDF" and len(out) > 500


def test_tolerates_empty_lists():
    out = render_meeting_pdf(Minutes(summary="s", decisions=[], action_items=[]), "x", META)
    assert out[:4] == b"%PDF"
