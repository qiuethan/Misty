from src.pipeline.transcript import assemble_transcript, format_timestamp


def test_format_timestamp():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65000) == "01:05"


def test_assemble_sorts_and_formats():
    segs = [
        {"speaker": "bob", "start_ms": 2000, "text": "hi"},
        {"speaker": "alice", "start_ms": 0, "text": "hello"},
    ]
    assert assemble_transcript(segs) == "[00:00] alice: hello\n[00:02] bob: hi"


def test_assemble_filters_empty_stable():
    segs = [
        {"speaker": "a", "start_ms": 0, "text": "x"},
        {"speaker": "b", "start_ms": 0, "text": "y"},
        {"speaker": "c", "start_ms": 5, "text": "  "},
    ]
    assert assemble_transcript(segs) == "[00:00] a: x\n[00:00] b: y"
