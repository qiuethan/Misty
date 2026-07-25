from src.pipeline.minutes import summarize_minutes


class FakeLlm:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        return self.content


def test_parses_json():
    llm = FakeLlm('{"summary":"s","decisions":["d"],"action_items":["a"]}')
    m = summarize_minutes("[00:00] x: hi", llm)
    assert m.summary == "s" and m.decisions == ["d"] and m.action_items == ["a"]
    assert "hi" in llm.calls[0]["messages"][-1]["content"]


def test_tolerates_fenced_json():
    llm = FakeLlm('```json\n{"summary":"s","decisions":[],"action_items":[]}\n```')
    assert summarize_minutes("x", llm).summary == "s"


def test_fallback_on_bad_json():
    llm = FakeLlm("not json")
    m = summarize_minutes("x", llm)
    assert m.summary == "not json" and m.decisions == [] and m.action_items == []
