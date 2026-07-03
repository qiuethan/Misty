"""Key hashing + generation for the API-key auth system.

Uses argon2 (recommended by OWASP for password hashing) for the stored key
hash. Argon2's parameters (memory, time, parallelism) are set at library
defaults, which is fine for a rarely-called auth path (once per request).
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

PREFIX_LENGTH = 8  # chars in the public prefix segment
KEY_ENVELOPE = "tt_"  # every key starts with this so we can cheaply reject stray headers


def generate_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (plaintext, prefix, key_hash). The plaintext MUST be shown to the
    caller exactly once (typically printed by a CLI) and then discarded.

    Format: tt_<prefix>_<secret>
    - prefix: 8 URL-safe base64 chars (stored plaintext for lookup)
    - secret: 32 raw bytes → ~43 URL-safe base64 chars
    """
    # Generate prefix without underscores so the tt_<prefix>_<secret> format
    # is unambiguous. token_urlsafe uses base64url (A-Z, a-z, 0-9, -, _);
    # we replace underscores with hyphens to keep the _ as sole separator.
    raw_prefix = secrets.token_urlsafe(12).replace("_", "-")
    prefix = raw_prefix[:PREFIX_LENGTH]  # 8 chars
    secret = secrets.token_urlsafe(32)
    plaintext = f"{KEY_ENVELOPE}{prefix}_{secret}"
    key_hash = _hasher.hash(plaintext)
    return plaintext, prefix, key_hash


def verify_key(candidate: str, key_hash: str) -> bool:
    """Constant-time verify a candidate plaintext against an argon2 hash.

    Returns True on match, False on any mismatch or malformed hash.
    """
    try:
        return _hasher.verify(key_hash, candidate)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed hash string, wrong hash type, etc. — treat as mismatch.
        # Never leak the reason.
        return False


def parse_prefix(candidate: str) -> str | None:
    """Extract the prefix segment from a candidate key.

    Returns the prefix string, or None if the candidate does not match the
    expected envelope format. The parse itself is O(1) and does no crypto —
    a malformed key just gets a fast rejection.
    """
    if not candidate.startswith(KEY_ENVELOPE):
        return None
    body = candidate[len(KEY_ENVELOPE) :]
    parts = body.split("_", 1)
    if len(parts) != 2 or len(parts[0]) != PREFIX_LENGTH:
        return None
    return parts[0]
