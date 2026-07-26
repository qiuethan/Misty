"""Render meeting minutes + transcript into a branded UTMIST PDF.

Layout: a cobalt masthead band on page 1 (UTMIST logo in a white chip +
"Meeting Minutes"), then the meeting title, an at-a-glance meta strip, and the
sections (Summary, Decisions, Action Items, Full Transcript). Structured
sections are tables; free-form ones are prose/bullets. A branded footer with
page numbers repeats on every page.

Uses bundled **DejaVu** (Unicode) TTFs, so accented names and non-latin scripts
(Cyrillic, Greek, …) render instead of being replaced with ``?`` (DejaVu does
not cover CJK or emoji — those degrade to a missing-glyph box, never a ``?``).
The only image is the logo; all text stays real text, so the PDF is fully
text-parsable (pdftotext, search, LLM re-ingest).
"""

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from src.contracts import Minutes

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_FONT_DIR = _ASSETS / "fonts"
_LOGO = _ASSETS / "brand" / "utmist-logo.png"

# UTMIST palette (derived from the logo's cobalt #002FCB)
_BRAND = (0, 47, 203)  # cobalt: masthead, headings, rules, table header, marks
_BRAND_TINT = (238, 241, 254)  # very light cobalt: transcript zebra + meta box
_INK = (26, 26, 26)
_MUTED = (110, 110, 110)  # meta strip, footer, "None recorded."
_RULE = (219, 219, 219)  # hairline rules
_WHITE = (255, 255, 255)

_BAND_H = 26.0  # masthead band height (mm)


class _MeetingPDF(FPDF):
    """FPDF with the bundled DejaVu families registered and a branded footer."""

    def __init__(self) -> None:
        super().__init__()
        self.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVuMono", "", str(_FONT_DIR / "DejaVuSansMono.ttf"))
        self.add_font("DejaVuMono", "B", str(_FONT_DIR / "DejaVuSansMono-Bold.ttf"))

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(*_RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(1.5)
        self.set_x(self.l_margin)
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(*_BRAND)
        self.cell(0, 6, "UTMIST", align="L", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 6, f"Page {self.page_no()} of {{nb}}", align="R")
        self.set_text_color(0, 0, 0)


def _line(pdf: FPDF, h: float, text: str) -> None:
    """multi_cell wrapper that always returns the cursor to the left margin."""
    pdf.multi_cell(0, h, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _rule(pdf: FPDF, gap_above: float = 1.0, gap_below: float = 0.0, color=_RULE) -> None:
    pdf.set_draw_color(*color)
    y = pdf.get_y() + gap_above
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_y(y + gap_below)


def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_text_color(*_BRAND)
    _line(pdf, 7, text)
    pdf.set_text_color(0, 0, 0)


def _muted_line(pdf: FPDF, text: str) -> None:
    pdf.set_font("DejaVu", "", 11)
    pdf.set_text_color(*_MUTED)
    _line(pdf, 6, text)
    pdf.set_text_color(0, 0, 0)


def _masthead(pdf: FPDF, title: str, meta_strip: str, participants_line: str) -> None:
    # Cobalt band across the top of page 1.
    pdf.set_fill_color(*_BRAND)
    pdf.rect(0, 0, pdf.w, _BAND_H, style="F")

    # White rounded chip holding the (light-background) logo.
    chip = 18.0
    cx, cy = pdf.l_margin, (_BAND_H - chip) / 2
    pdf.set_fill_color(*_WHITE)
    pdf.rect(cx, cy, chip, chip, style="F", round_corners=True, corner_radius=2.5)
    pad = 2.0
    box = chip - 2 * pad
    # Preserve the logo's aspect ratio (600x672) inside the chip.
    logo_w, logo_h = 600.0, 672.0
    draw_h = box
    draw_w = draw_h * (logo_w / logo_h)
    if draw_w > box:
        draw_w = box
        draw_h = draw_w * (logo_h / logo_w)
    pdf.image(
        str(_LOGO),
        x=cx + (chip - draw_w) / 2,
        y=cy + (chip - draw_h) / 2,
        w=draw_w,
        h=draw_h,
    )

    # "Meeting Minutes" in white, vertically centered next to the chip (the
    # logo already carries the UTMIST wordmark).
    pdf.set_font("DejaVu", "B", 15)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(cx + chip + 5, (_BAND_H - 7) / 2)
    pdf.cell(0, 7, "Meeting Minutes", new_x=XPos.LMARGIN, new_y=YPos.TOP)
    pdf.set_text_color(0, 0, 0)

    # Below the band: meeting title + at-a-glance meta + participants.
    pdf.set_y(_BAND_H + 5)
    pdf.set_font("DejaVu", "B", 19)
    pdf.set_text_color(*_BRAND)
    _line(pdf, 9, title)
    pdf.set_text_color(0, 0, 0)

    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*_MUTED)
    if meta_strip:
        _line(pdf, 5.5, meta_strip)
    _line(pdf, 5.5, participants_line)
    pdf.set_text_color(0, 0, 0)
    _rule(pdf, gap_above=2, gap_below=2)


def _bulleted(pdf: FPDF, items: list[str]) -> None:
    pdf.set_font("DejaVu", "", 11)
    if not items:
        _muted_line(pdf, "None recorded.")
        return
    for item in items:
        _line(pdf, 6, f"• {item}")  # • bullet (real Unicode now that fonts allow it)


def _action_items(pdf: FPDF, items: list[str]) -> None:
    if not items:
        _muted_line(pdf, "None recorded.")
        return
    pdf.set_font("DejaVu", "", 11)
    with pdf.table(
        borders_layout="NONE",
        first_row_as_headings=False,
        col_widths=(7, 145),
        text_align=("CENTER", "LEFT"),
        line_height=6,
        width=pdf.epw,
    ) as table:
        for item in items:
            row = table.row()
            row.cell("☐")  # ballot box: an open checkbox
            row.cell(item)


def _parse_turn(line: str) -> tuple[str, str, str]:
    """Split an ``assemble_transcript`` line ``[HH:MM:SS] speaker: text`` into
    ``(time, speaker, text)``. Lines that don't match go entirely in the text
    column with empty time/speaker."""
    if line.startswith("[") and "] " in line:
        ts, after = line.split("] ", 1)
        speaker, sep, text = after.partition(": ")
        if sep:
            return ts.lstrip("[").strip(), speaker.strip(), text.strip()
    return "", "", line.strip()


def _transcript(pdf: FPDF, transcript: str) -> None:
    lines = [ln for ln in (transcript or "").split("\n") if ln.strip()]
    if not lines:
        _muted_line(pdf, "None recorded.")
        return
    pdf.set_font("DejaVu", "", 9)
    with pdf.table(
        borders_layout="HORIZONTAL_LINES",
        headings_style=FontFace(emphasis="BOLD", color=_WHITE, fill_color=_BRAND),
        col_widths=(16, 26, 110),
        text_align=("LEFT", "LEFT", "LEFT"),
        cell_fill_mode="ROWS",
        cell_fill_color=_BRAND_TINT,
        line_height=5,
        width=pdf.epw,
    ) as table:
        table.row(("Time", "Speaker", "Text"))
        for line in lines:
            ts, speaker, text = _parse_turn(line)
            row = table.row()
            row.cell(ts, style=FontFace(family="DejaVuMono"))
            row.cell(speaker, style=FontFace(emphasis="BOLD"))
            row.cell(text)


def _meta_strip(meta: dict, minutes: Minutes) -> tuple[str, str]:
    """Build the at-a-glance strip ('date · duration · N participants · N action
    items') and the full participants line."""
    participants = meta.get("participants", []) or []
    parts = []
    if meta.get("started_at"):
        parts.append(str(meta["started_at"]))
    if meta.get("duration_label"):
        parts.append(str(meta["duration_label"]))
    parts.append(f"{len(participants)} participant" + ("" if len(participants) == 1 else "s"))
    n_actions = len(minutes.action_items)
    if n_actions:
        parts.append(f"{n_actions} action item" + ("" if n_actions == 1 else "s"))
    strip = "   ·   ".join(parts)
    participants_line = "Participants: " + (", ".join(participants) if participants else "None recorded.")
    return strip, participants_line


def _document_title(minutes: Minutes, meta: dict) -> str:
    """The big meeting title: the LLM-generated title, falling back to a
    caller-supplied meta title, then a static default."""
    return (
        (getattr(minutes, "title", "") or "").strip()
        or (meta.get("title") or "").strip()
        or "Meeting Minutes"
    )


def render_meeting_pdf(minutes: Minutes, transcript: str, meta: dict) -> bytes:
    pdf = _MeetingPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    strip, participants_line = _meta_strip(meta, minutes)
    _masthead(pdf, _document_title(minutes, meta), strip, participants_line)

    # Summary
    _heading(pdf, "Summary")
    if minutes.summary:
        pdf.set_font("DejaVu", "", 11)
        _line(pdf, 6, minutes.summary)
    else:
        _muted_line(pdf, "None recorded.")

    # Decisions (bullets)
    _heading(pdf, "Decisions")
    _bulleted(pdf, minutes.decisions)

    # Action Items (checklist table)
    _heading(pdf, "Action Items")
    _action_items(pdf, minutes.action_items)

    # Full Transcript (Time / Speaker / Text table)
    _heading(pdf, "Full Transcript")
    _transcript(pdf, transcript)

    return bytes(pdf.output())
