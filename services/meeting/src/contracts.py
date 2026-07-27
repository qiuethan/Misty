from pydantic import BaseModel


class Minutes(BaseModel):
    title: str = ""  # LLM-generated meeting title (empty -> PDF uses a fallback)
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
