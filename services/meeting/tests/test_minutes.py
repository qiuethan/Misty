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
