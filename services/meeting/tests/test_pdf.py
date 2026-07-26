from src.contracts import Minutes
from src.pipeline.pdf import render_meeting_pdf

META = {"title": "T", "started_at": "2026-07-25 18:00", "duration_label": "12m", "participants": ["a", "b"]}


def test_returns_pdf_bytes():
    out = render_meeting_pdf(Minutes(summary="s", decisions=["d"], action_items=["a"]), "[00:00] a: hi", META)
    assert isinstance(out, (bytes, bytearray)) and out[:4] == b"%PDF" and len(out) > 0


def test_tolerates_empty_lists():
    out = render_meeting_pdf(Minutes(summary="s", decisions=[], action_items=[]), "x", META)
    assert out[:4] == b"%PDF"


def test_embeds_unicode_font_and_renders_non_latin():
    """The point of the DejaVu switch: non-latin names/utterances must survive
    into the PDF instead of being replaced with '?'. Prove it by rendering
    accented + Cyrillic + Greek text (all covered by DejaVu) and asserting a
    DejaVu (Unicode) font subset is embedded -- with the old latin-1 core fonts
    no TTF was embedded and these characters went through a lossy '?'
    replacement. (CJK/emoji are out of DejaVu's coverage and degrade to a
    missing-glyph box, not a '?'.)"""
    meta = {**META, "title": "Café planning — σύνοδος", "participants": ["José", "Даша", "Γιώργος"]}
    minutes = Minutes(
        summary="Discussed the café rollout — décisions finales.",
        decisions=["Ship the piñata feature", "Найти площадку"],
        action_items=["José: résumé the spec"],
    )
    transcript = "[00:00:01] José: allô, ça va?\n[00:00:05] Даша: да, начнём"

    out = render_meeting_pdf(minutes, transcript, meta)

    assert out[:4] == b"%PDF"
    assert b"DejaVu" in out  # a DejaVu font subset is embedded -> Unicode path taken


def test_paginates_and_resolves_page_number_alias():
    """A long transcript spans multiple pages, exercising the footer on every
    page; the '{nb}' total-pages placeholder must be resolved to a real number
    in the output (never left literal)."""
    transcript = "\n".join(
        f"[00:{i // 60:02d}:{i % 60:02d}] speaker{i % 3}: line number {i} of the meeting" for i in range(400)
    )
    out = render_meeting_pdf(Minutes(summary="s", decisions=[], action_items=[]), transcript, META)
    small = render_meeting_pdf(Minutes(summary="s", decisions=[], action_items=[]), "[00:00] a: hi", META)

    assert out[:4] == b"%PDF"
    assert b"{nb}" not in out  # page-count alias was substituted
    assert len(out) > len(small)  # multi-page doc is materially larger
