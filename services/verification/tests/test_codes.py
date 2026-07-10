import re

from src.codes import generate_code, hash_code, verify_code


def test_generate_code_is_six_digits():
    for _ in range(50):
        assert re.fullmatch(r"\d{6}", generate_code())


def test_hash_is_deterministic():
    assert hash_code("123456", "secret") == hash_code("123456", "secret")


def test_hash_differs_by_secret():
    assert hash_code("123456", "s1") != hash_code("123456", "s2")


def test_verify_true_and_false():
    h = hash_code("123456", "secret")
    assert verify_code("123456", h, "secret") is True
    assert verify_code("000000", h, "secret") is False
