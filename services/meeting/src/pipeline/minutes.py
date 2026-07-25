import json
import re

from src.contracts import Minutes

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
    content = llm_client.chat(
        system=MINUTES_SYSTEM_PROMPT,
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript}"}],
    )
    parsed = _extract_json(content)
    if not parsed or not isinstance(parsed.get("summary"), str):
        return Minutes(summary=(content or "").strip(), decisions=[], action_items=[])
    return Minutes(
        summary=parsed["summary"],
        decisions=[
            str(x)
            for x in parsed.get("decisions", [])
            if isinstance(parsed.get("decisions"), list)
        ],
        action_items=[
            str(x)
            for x in parsed.get("action_items", [])
            if isinstance(parsed.get("action_items"), list)
        ],
    )
