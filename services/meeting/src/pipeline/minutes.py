import json
import logging
import re

from src.contracts import Minutes
from src.pipeline.llm_client import LlmUnavailable

_logger = logging.getLogger(__name__)

# The llm service permits far more; 1500 was low enough that a busy meeting's
# minutes were routinely truncated mid-JSON.
MINUTES_MAX_TOKENS = 4000

# Salvage tries checkpoints newest-first, and each attempt costs a json.loads
# over a growing prefix -- so an unsalvageable fragment would otherwise walk
# every one, quadratically. A usable recovery point is essentially always within
# a few checkpoints of the truncation, and the response is untrusted input from
# a network service, so cap the search.
_MAX_SALVAGE_ATTEMPTS = 64

# A bracket followed by a quoted key/element. Deliberately narrow: it should
# catch a JSON fragment wrapped in a fence or introduced by a lead-in sentence
# ("Here are the minutes:\n{\"title\"...") without misfiring on ordinary prose,
# which rarely contains `{"`.
_JSON_ISH = re.compile(r'[\{\[]\s*"')

MINUTES_SYSTEM_PROMPT = (
    "You write concise meeting minutes for a student organization. Given a "
    "timestamped transcript, respond with ONLY a JSON object of shape "
    '{"title": string, "summary": string, "decisions": string[], "action_items": string[]}. '
    "title is a short, specific meeting title of at most 8 words that captures "
    "what the meeting was about (no surrounding quotes, no trailing punctuation), "
    'e.g. "Weekly Sync: Q3 Roadmap & Hiring". summary is 2-5 sentences. No prose '
    "outside the JSON."
)


def _candidate(text: str) -> str:
    """The JSON-looking region of a model response, unwrapped from any fence."""
    t = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    return fenced.group(1).strip() if fenced else t


def _salvage_truncated(cand: str):
    """Parse a JSON object that was cut off mid-write.

    The model is capped at ``MINUTES_MAX_TOKENS``, so a long meeting can have
    its response truncated at an arbitrary point. Rather than discarding
    everything (which used to dump the raw fragment into the summary field), we
    rewind to a position where the document was structurally complete and close
    whatever is still open.

    Two kinds of recovery point, tried in that order:

    1. **Clean boundaries** -- a value has just finished. Preferred, because a
       recovered top-level string is always complete. (A boundary can still
       land inside a NESTED object and keep a partial one; harmless under the
       string[] schema this prompt asks for, but not a guarantee.)
    2. **Inside a string** -- close the string where it was cut. Only used when
       no clean boundary yields a summary, i.e. the truncation landed in the
       summary itself, where a partial sentence beats losing it entirely.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    clean: list[tuple[int, str]] = []

    for idx, ch in enumerate(cand):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                clean.append((idx + 1, "".join(reversed(stack))))
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            clean.append((idx + 1, "".join(reversed(stack))))

    def _parse(head: str, closers: str):
        try:
            value = json.loads(head + closers)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    best = None
    for cut, closers in reversed(clean[-_MAX_SALVAGE_ATTEMPTS:]):
        parsed = _parse(cand[:cut], closers)
        if parsed is None:
            continue
        if isinstance(parsed.get("summary"), str):
            return parsed
        if best is None:
            best = parsed

    if in_string:
        # Close the string exactly where it was cut, dropping a dangling escape
        # that would otherwise make the closing quote invalid.
        head = cand[:-1] if escaped else cand
        parsed = _parse(head, '"' + "".join(reversed(stack)))
        if parsed is not None and isinstance(parsed.get("summary"), str):
            return parsed
        if best is None:
            best = parsed

    return best


def _extract_json(text: str):
    cand = _candidate(text)
    i, j = cand.find("{"), cand.rfind("}")
    if i != -1 and j != -1 and j > i:
        try:
            return json.loads(cand[i : j + 1])
        except ValueError:
            pass
    if i == -1:
        return None
    salvaged = _salvage_truncated(cand[i:])
    if salvaged is not None:
        # A salvaged response is a LOSSY success: whatever the model wrote after
        # the truncation is gone, so the PDF can look authoritative while a
        # decision it actually made is missing. Say so.
        _logger.warning(
            "salvaged truncated minutes JSON from a %s-char response; "
            "content after the truncation point is lost",
            len(cand),
        )
    return salvaged


def summarize_minutes(transcript: str, llm_client, model=None) -> Minutes:
    try:
        content = llm_client.chat(
            system=MINUTES_SYSTEM_PROMPT,
            model=model,
            max_tokens=MINUTES_MAX_TOKENS,
            messages=[{"role": "user", "content": f"Transcript:\n\n{transcript}"}],
        )
    except LlmUnavailable as exc:
        _logger.warning("LLM unavailable, returning placeholder minutes: %s", exc)
        return Minutes(
            summary="(minutes unavailable: LLM service error)", decisions=[], action_items=[]
        )
    parsed = _extract_json(content)
    if not parsed or not isinstance(parsed.get("summary"), str):
        # Last resort: the model wrote prose instead of JSON, or the response was
        # too mangled to salvage. Use it as the summary -- but never a raw JSON
        # fragment, which is unreadable in the PDF and used to be what a reader
        # actually saw when the response was truncated.
        fallback = (content or "").strip()
        # Check the UNWRAPPED candidate: a truncated response never closes its
        # fence, so a bare startswith("{") misses ```json blocks and "Here are
        # the minutes:" lead-ins -- the two commonest shapes -- and the raw
        # fragment reaches the reader anyway.
        unwrapped = _candidate(fallback).lstrip()
        if unwrapped.startswith(("{", "[")) or _JSON_ISH.search(fallback):
            _logger.warning(
                "could not parse or salvage minutes JSON (%s chars); "
                "returning a placeholder summary",
                len(fallback),
            )
            fallback = "(minutes unavailable: the model's response could not be parsed)"
        return Minutes(summary=fallback, decisions=[], action_items=[])
    raw_decisions = parsed.get("decisions", [])
    raw_action_items = parsed.get("action_items", [])
    raw_title = parsed.get("title")
    return Minutes(
        title=str(raw_title).strip()[:120] if isinstance(raw_title, str) else "",
        summary=parsed["summary"],
        decisions=[str(x) for x in raw_decisions] if isinstance(raw_decisions, list) else [],
        action_items=[str(x) for x in raw_action_items] if isinstance(raw_action_items, list) else [],
    )
