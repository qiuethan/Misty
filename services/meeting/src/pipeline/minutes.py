import json
import re

from src.contracts import Minutes
from src.pipeline.llm_client import LlmUnavailable

MINUTES_SYSTEM_PROMPT = (
    "You write concise meeting minutes for a student organization. Given a "
    "timestamped transcript, respond with ONLY a JSON object of shape "
    '{"summary": string, "decisions": string[], "action_items": string[]}. '
    "summary is 2-5 sentences. No prose outside the JSON."
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
    except LlmUnavailable:
        return Minutes(
            summary="(minutes unavailable: LLM service error)", decisions=[], action_items=[]
        )
    parsed = _extract_json(content)
    if not parsed or not isinstance(parsed.get("summary"), str):
        return Minutes(summary=(content or "").strip(), decisions=[], action_items=[])
    raw_decisions = parsed.get("decisions", [])
    raw_action_items = parsed.get("action_items", [])
    return Minutes(
        summary=parsed["summary"],
        decisions=[str(x) for x in raw_decisions] if isinstance(raw_decisions, list) else [],
        action_items=[str(x) for x in raw_action_items] if isinstance(raw_action_items, list) else [],
    )
