from datetime import datetime

from contracts.types import VerificationCode


class InMemoryVerificationStore:
    """In-process store used in tests and quick prototyping. Not persistent."""

    def __init__(self) -> None:
        self._by_subject: dict[str, VerificationCode] = {}

    def create_code(self, code: VerificationCode) -> None:
        self._by_subject[code.subject] = code

    def get_code(self, subject: str) -> VerificationCode | None:
        return self._by_subject.get(subject)

    def latest_unconsumed_for_email(self, email: str) -> VerificationCode | None:
        candidates = [
            c for c in self._by_subject.values() if c.email == email and c.consumed_at is None
        ]
        return max(candidates, key=lambda c: c.created_at) if candidates else None

    def increment_attempts(self, subject: str) -> int:
        code = self._by_subject.get(subject)
        if code is None:
            return 0
        new_attempts = code.attempts + 1
        self._by_subject[subject] = code.model_copy(update={"attempts": new_attempts})
        return new_attempts

    def mark_consumed(self, subject: str, consumed_at: datetime) -> None:
        code = self._by_subject.get(subject)
        if code is not None:
            self._by_subject[subject] = code.model_copy(update={"consumed_at": consumed_at})
