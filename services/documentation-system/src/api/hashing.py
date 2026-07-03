"""Key hashing + generation for the API-key auth system (argon2)."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

PREFIX_LENGTH = 8
KEY_ENVELOPE = "doc_"


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, key_hash). Plaintext shown once. Format:
    doc_<prefix>_<secret>."""
    raw_prefix = secrets.token_urlsafe(12).replace("_", "-")
    prefix = raw_prefix[:PREFIX_LENGTH]
    secret = secrets.token_urlsafe(32)
    plaintext = f"{KEY_ENVELOPE}{prefix}_{secret}"
    key_hash = _hasher.hash(plaintext)
    return plaintext, prefix, key_hash


def verify_key(candidate: str, key_hash: str) -> bool:
    try:
        return _hasher.verify(key_hash, candidate)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def parse_prefix(candidate: str) -> str | None:
    if not candidate.startswith(KEY_ENVELOPE):
        return None
    body = candidate[len(KEY_ENVELOPE):]
    parts = body.split("_", 1)
    if len(parts) != 2 or len(parts[0]) != PREFIX_LENGTH:
        return None
    return parts[0]
