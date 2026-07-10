import hashlib
import hmac
import secrets

from src.policy import CODE_LENGTH


def generate_code() -> str:
    """Return a zero-padded numeric one-time code (CODE_LENGTH digits)."""
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def hash_code(code: str, secret: str) -> str:
    """HMAC-SHA256 of the code under a server secret; hex digest."""
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def verify_code(code: str, code_hash: str, secret: str) -> bool:
    """Constant-time comparison of a candidate code against a stored hash."""
    return hmac.compare_digest(hash_code(code, secret), code_hash)
