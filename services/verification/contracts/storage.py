from datetime import datetime
from typing import Protocol

from contracts.types import VerificationCode


class VerificationStore(Protocol):
    """Contract between the API and the code-persistence layer.

    Invariant: at most one live row per subject. `create_code` replaces any
    existing row for that subject (supersede-on-reissue).
    """

    def create_code(self, code: VerificationCode) -> None: ...
    def get_code(self, subject: str) -> VerificationCode | None: ...
    def latest_unconsumed_for_email(self, email: str) -> VerificationCode | None: ...
    def increment_attempts(self, subject: str) -> int:
        """Atomically bump the subject's attempt counter and return the new value.

        Must be a single atomic operation so concurrent confirm-code requests
        cannot lose increments and slip past the attempt-lockout. Returns 0 if
        no row exists for the subject.
        """
        ...

    def mark_consumed(self, subject: str, consumed_at: datetime) -> None: ...
