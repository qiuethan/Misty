import json
import logging
import re

from src.contracts import Minutes
from src.pipeline.llm_client import LlmUnavailable

_logger = logging.getLogger(__name__)

MINUTES_SYSTEM_PROMPT = (
    "You write concise meeting minutes for a student organization. Given a "
    "timestamped transcript, respond with ONLY a JSON object of shape "
    '{"title": string, "summary": string, "decisions": string[], "action_items": string[]}. '
    "title is a short, specific meeting title of at most 8 words that captures "
    "what the meeting was about (no surrounding quotes, no trailing punctuation), "
    'e.g. "Weekly Sync: Q3 Roadmap & Hiring". summary is 2-5 sentences. No prose '
    "outside the JSON."
)


def _extract_json(text: str):
    t = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    cand = fenced.group(1).strip() if fenced else t
    i, j = cand.find("{"), cand.rfind("}")
    if i == -1 or j == -1 or j < i:
        return None
    try:
        return json.loads(cand[i : j + 1])
    except ValueError:
        return None


def summarize_minutes(transcript: str, llm_client, model=None) -> Minutes:
    try:
        content = llm_client.chat(
            system=MINUTES_SYSTEM_PROMPT,
            model=model,
            max_tokens=1500,
            messages=[{"role": "user", "content": f"Transcript:\n\n{transcript}"}],
        )
    except LlmUnavailable as exc:
        _logger.warning("LLM unavailable, returning placeholder minutes: %s", exc)
        return Minutes(
            summary="(minutes unavailable: LLM service error)", decisions=[], action_items=[]
        )
    parsed = _extract_json(content)
    if not parsed or not isinstance(parsed.get("summary"), str):
        return Minutes(summary=(content or "").strip(), decisions=[], action_items=[])
    raw_decisions = parsed.get("decisions", [])
    raw_action_items = parsed.get("action_items", [])
    raw_title = parsed.get("title")
    return Minutes(
        title=str(raw_title).strip()[:120] if isinstance(raw_title, str) else "",
        summary=parsed["summary"],
        decisions=[str(x) for x in raw_decisions] if isinstance(raw_decisions, list) else [],
        action_items=[str(x) for x in raw_action_items] if isinstance(raw_action_items, list) else [],
    )
