from src.api.hashing import KEY_ENVELOPE, generate_key, parse_prefix, verify_key


def test_generate_key_envelope_and_roundtrip():
    plaintext, prefix, key_hash = generate_key()
    assert plaintext.startswith("doc_")
    assert KEY_ENVELOPE == "doc_"
    assert parse_prefix(plaintext) == prefix
    assert verify_key(plaintext, key_hash) is True
    assert verify_key("doc_wrong_key", key_hash) is False


def test_parse_prefix_rejects_foreign_envelope():
    assert parse_prefix("tt_abc_def") is None
    assert parse_prefix("garbage") is None
