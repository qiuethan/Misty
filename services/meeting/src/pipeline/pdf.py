"""Render meeting minutes + transcript into a PDF using fpdf2 core fonts."""

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from src.contracts import Minutes


def _safe(text: str) -> str:
    """Core fonts (Helvetica/Courier) are latin-1 only; replace unsupported chars."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _line(pdf: FPDF, h: float, text: str) -> None:
    """multi_cell wrapper that always returns the cursor to the left margin."""
    pdf.multi_cell(0, h, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _bulleted(pdf: FPDF, items: list[str]) -> None:
    pdf.set_font("Helvetica", size=11)
    if not items:
        pdf.set_font("Helvetica", style="I", size=11)
        _line(pdf, 6, _safe("None recorded."))
        pdf.set_font("Helvetica", size=11)
        return
    for item in items:
        _line(pdf, 6, _safe(f"- {item}"))


def render_meeting_pdf(minutes: Minutes, transcript: str, meta: dict) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    # Title / meta header
    pdf.set_font("Helvetica", style="B", size=18)
    _line(pdf, 10, _safe(meta.get("title", "Meeting Minutes")))

    pdf.set_font("Helvetica", size=10)
    started_at = meta.get("started_at", "")
    duration_label = meta.get("duration_label", "")
    participants = meta.get("participants", []) or []
    _line(pdf, 6, _safe(f"Started: {started_at}    Duration: {duration_label}"))
    _line(pdf, 6, _safe(f"Participants: {', '.join(participants) if participants else 'None recorded.'}"))
    pdf.ln(4)

    # Summary
    pdf.set_font("Helvetica", style="B", size=14)
    _line(pdf, 8, "Summary")
    pdf.set_font("Helvetica", size=11)
    _line(pdf, 6, _safe(minutes.summary or "None recorded."))
    pdf.ln(4)

    # Decisions
    pdf.set_font("Helvetica", style="B", size=14)
    _line(pdf, 8, "Decisions")
    _bulleted(pdf, minutes.decisions)
    pdf.ln(4)

    # Action Items
    pdf.set_font("Helvetica", style="B", size=14)
    _line(pdf, 8, "Action Items")
    _bulleted(pdf, minutes.action_items)
    pdf.ln(4)

    # Full Transcript
    pdf.set_font("Helvetica", style="B", size=14)
    _line(pdf, 8, "Full Transcript")
    pdf.set_font("Courier", size=9)
    _line(pdf, 5, _safe(transcript or "None recorded."))

    return bytes(pdf.output())
