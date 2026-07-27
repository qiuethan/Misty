from src.pipeline.llm_client import LlmUnavailable
from src.pipeline.minutes import summarize_minutes


class FakeLlm:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        return self.content


class FailingLlm:
    def chat(self, **kw):
        raise LlmUnavailable("boom")


def test_parses_json():
    llm = FakeLlm('{"summary":"s","decisions":["d"],"action_items":["a"]}')
    m = summarize_minutes("[00:00] x: hi", llm)
    assert m.summary == "s" and m.decisions == ["d"] and m.action_items == ["a"]
    assert "hi" in llm.calls[0]["messages"][-1]["content"]


def test_parses_llm_title():
    llm = FakeLlm('{"title":"Q3 Roadmap Sync","summary":"s","decisions":[],"action_items":[]}')
    assert summarize_minutes("x", llm).title == "Q3 Roadmap Sync"


def test_title_defaults_empty_when_absent_or_non_string():
    assert summarize_minutes("x", FakeLlm('{"summary":"s"}')).title == ""
    assert summarize_minutes("x", FakeLlm('{"title":123,"summary":"s"}')).title == ""


def test_tolerates_fenced_json():
    llm = FakeLlm('```json\n{"summary":"s","decisions":[],"action_items":[]}\n```')
    assert summarize_minutes("x", llm).summary == "s"


def test_fallback_on_bad_json():
    llm = FakeLlm("not json")
    m = summarize_minutes("x", llm)
    assert m.summary == "not json" and m.decisions == [] and m.action_items == []


def test_null_or_scalar_list_fields_fall_back_to_empty():
    llm = FakeLlm('{"summary":"s","decisions":null,"action_items":5}')
    m = summarize_minutes("x", llm)
    assert m.summary == "s"
    assert m.decisions == []
    assert m.action_items == []


def test_degrades_to_placeholder_minutes_on_llm_outage():
    # A transient LLM outage must not lose the whole meeting (transcript/PDF/audio
    # still get delivered) — summarize_minutes degrades instead of propagating.
    m = summarize_minutes("x", FailingLlm())
    assert m.summary == "(minutes unavailable: LLM service error)"
    assert m.decisions == []
    assert m.action_items == []
    assert m.title == ""  # no title on outage -> PDF uses its fallback


# --- truncated LLM responses -------------------------------------------------
#
# The model is capped at max_tokens, so a long meeting can have its JSON cut off
# mid-write. Before this was handled, `_extract_json` returned None and the
# fallback put the RAW TRUNCATED JSON in the summary field -- so the PDF showed
# a wall of JSON ending mid-word, with no decisions or action items at all.

_TRUNCATED_MID_ARRAY = (
    '{"title": "Weekly Sync: Q3 Roadmap", '
    '"summary": "The team reviewed the roadmap and agreed on hiring priorities.", '
    '"decisions": ["Ship the beta on Friday", "Defer the redesign to Q4"], '
    '"action_items": ["Ethan to draft the spec", "Priya to review the bud'
)

_TRUNCATED_MID_STRING = (
    '{"title": "Weekly Sync", '
    '"summary": "The team reviewed the roadmap and agreed on hiring priorities '
    'for the coming quarter, then moved on to discussing the budg'
)


def test_salvages_a_response_truncated_mid_array():
    """Everything the model DID finish must survive: title, summary, all
    decisions, and the action items it completed."""
    m = summarize_minutes("x", FakeLlm(_TRUNCATED_MID_ARRAY))

    assert m.title == "Weekly Sync: Q3 Roadmap"
    assert m.summary == "The team reviewed the roadmap and agreed on hiring priorities."
    assert m.decisions == ["Ship the beta on Friday", "Defer the redesign to Q4"]
    assert m.action_items == ["Ethan to draft the spec"]


def test_salvages_a_response_truncated_mid_string():
    """Cut off inside the summary itself: keep the title, and keep the partial
    summary as readable prose rather than losing it."""
    m = summarize_minutes("x", FakeLlm(_TRUNCATED_MID_STRING))

    assert m.title == "Weekly Sync"
    assert m.summary.startswith("The team reviewed the roadmap")
    assert m.decisions == []


def test_never_surfaces_raw_json_as_the_summary():
    """Whatever happens, the summary is prose for a human -- never a dump of the
    model's raw JSON, which is what a reader used to see in the PDF."""
    for content in (_TRUNCATED_MID_ARRAY, _TRUNCATED_MID_STRING, '{"summary": "ok"'):
        summary = summarize_minutes("x", FakeLlm(content)).summary
        assert not summary.lstrip().startswith("{"), f"raw JSON leaked into summary: {summary[:60]}"
        assert '"action_items"' not in summary
        assert '"decisions"' not in summary


def test_unparseable_prose_still_becomes_the_summary():
    """A model that ignores the JSON instruction and writes prose should still
    produce usable minutes -- existing behaviour, pinned so the salvage path
    doesn't regress it."""
    m = summarize_minutes("x", FakeLlm("We agreed to ship on Friday."))
    assert m.summary == "We agreed to ship on Friday."


def test_asks_for_enough_output_tokens_for_a_long_meeting():
    """1500 was low enough that a busy meeting's minutes were routinely cut off;
    the llm service allows far more."""
    llm = FakeLlm('{"summary":"s"}')
    summarize_minutes("x", llm)
    assert llm.calls[0]["max_tokens"] >= 4000
