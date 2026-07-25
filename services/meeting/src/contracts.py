from pydantic import BaseModel


class Minutes(BaseModel):
    summary: str
    decisions: list[str] = []
    action_items: list[str] = []
