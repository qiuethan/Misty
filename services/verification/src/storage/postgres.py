from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine

from contracts.types import VerificationCode
from src.storage.schema import verification_codes


def _row_to_code(row) -> VerificationCode:
    return VerificationCode(
        subject=row.subject,
        email=row.email,
        code_hash=row.code_hash,
        expires_at=row.expires_at,
        attempts=row.attempts,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


class PostgresVerificationStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_code(self, code: VerificationCode) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                delete(verification_codes).where(verification_codes.c.subject == code.subject)
            )
            conn.execute(
                insert(verification_codes).values(
                    subject=code.subject,
                    email=code.email,
                    code_hash=code.code_hash,
                    expires_at=code.expires_at,
                    attempts=code.attempts,
                    consumed_at=code.consumed_at,
                    created_at=code.created_at,
                )
            )

    def get_code(self, subject: str) -> VerificationCode | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(verification_codes).where(verification_codes.c.subject == subject)
            ).first()
        return _row_to_code(row) if row is not None else None

    def latest_unconsumed_for_email(self, email: str) -> VerificationCode | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(verification_codes)
                .where(verification_codes.c.email == email)
                .where(verification_codes.c.consumed_at.is_(None))
                .order_by(verification_codes.c.created_at.desc())
                .limit(1)
            ).first()
        return _row_to_code(row) if row is not None else None

    def set_attempts(self, subject: str, attempts: int) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(verification_codes)
                .where(verification_codes.c.subject == subject)
                .values(attempts=attempts)
            )

    def mark_consumed(self, subject: str, consumed_at: datetime) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(verification_codes)
                .where(verification_codes.c.subject == subject)
                .values(consumed_at=consumed_at)
            )
