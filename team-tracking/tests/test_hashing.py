"""Tests for the hashing/generation helpers."""

from src.api.hashing import KEY_ENVELOPE, PREFIX_LENGTH, generate_key, parse_prefix, verify_key


def test_generate_key_format():
    plaintext, prefix, key_hash = generate_key()
    assert plaintext.startswith(KEY_ENVELOPE)
    assert len(prefix) == PREFIX_LENGTH
    assert key_hash.startswith("$argon2")
    assert parse_prefix(plaintext) == prefix


def test_verify_roundtrip():
    plaintext, _, key_hash = generate_key()
    assert verify_key(plaintext, key_hash) is True


def test_verify_wrong_key_returns_false():
    _, _, key_hash = generate_key()
    other, _, _ = generate_key()
    assert verify_key(other, key_hash) is False


def test_verify_malformed_hash_returns_false():
    # Never raises; always returns False
    assert verify_key("anything", "not-an-argon2-hash") is False


def test_parse_prefix_rejects_bad_formats():
    assert parse_prefix("no-envelope") is None
    assert parse_prefix("tt_") is None                    # no body
    assert parse_prefix("tt_ab_secret") is None           # prefix too short
    assert parse_prefix("tt_abcdefghij_secret") is None   # prefix too long
    assert parse_prefix("tt_12345678_secret") == "12345678"


def test_two_generated_keys_are_distinct():
    a, ap, ah = generate_key()
    b, bp, bh = generate_key()
    assert a != b
    assert ap != bp
    assert ah != bh
