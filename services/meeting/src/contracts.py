from pydantic import BaseModel


class Minutes(BaseModel):
    summary: str
    decisions: list[str] = []
    action_items: list[str] = []


class Segment(BaseModel):
    speaker: str
    start_ms: int
    text: str


class TranscriptView(BaseModel):
    segments: list[Segment] = []


class StopResponse(BaseModel):
    transcript: str
    minutes: Minutes
    pdf_b64: str
    audio_b64: str | None = None
